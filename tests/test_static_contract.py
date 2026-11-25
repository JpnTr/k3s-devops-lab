import importlib.util
import json
import re
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lab_controller", ROOT / "scripts/lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class StaticContractTests(unittest.TestCase):
    def test_make_help_lists_declared_public_targets(self):
        makefile = (ROOT / "Makefile").read_text()
        targets = {line.split(":", 1)[0] for line in makefile.splitlines() if line and not line[0].isspace() and ":" in line}
        expected = {
            "help", "preflight", "up", "doctor", "urls", "lab-list", "lab-status",
            "lab-start", "lab-verify", "lab-reset", "diagnostics", "down",
            "validate", "lint", "test", "lab-suite",
        }
        help_line = next(line for line in makefile.splitlines() if "K3s DevOps Lab targets:" in line)
        self.assertTrue(expected <= targets)
        self.assertTrue(all(target in help_line for target in expected))

    def test_python_direct_requirements_are_exactly_pinned_without_duplicates(self):
        requirement_pattern = re.compile(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9.!+_-]*")
        for relative in ("app/requirements.txt", "requirements-dev.txt"):
            lines = [line.strip() for line in (ROOT / relative).read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
            self.assertTrue(lines)
            self.assertTrue(all(requirement_pattern.fullmatch(line) for line in lines), relative)
            normalized_names = [re.sub(r"[-_.]+", "-", line.split("==", 1)[0].split("[", 1)[0]).lower() for line in lines]
            self.assertEqual(len(normalized_names), len(set(normalized_names)), relative)
        api_python = re.match(r"python:(\d+\.\d+\.\d+)", yaml.safe_load((ROOT / "versions.yaml").read_text())["images"]["api"])
        self.assertIsNotNone(api_python)
        self.assertEqual(tuple(int(part) for part in api_python.group(1).split(".")), lab.PINNED_PYTHON_VERSION)

    def test_kustomize_inputs_are_present_and_controller_validates_before_mutation(self):
        kustomization_path = ROOT / "observability/kustomization.yaml"
        kustomization = yaml.safe_load(kustomization_path.read_text())
        for resource in kustomization["resources"]:
            self.assertTrue((kustomization_path.parent / resource).exists(), resource)
        for generator in kustomization.get("configMapGenerator", []):
            for source in generator.get("files", []):
                self.assertTrue((kustomization_path.parent / source.split("=", 1)[-1]).is_file(), source)
        controller = (ROOT / "scripts/lab.py").read_text()
        baseline = controller.split("def baseline():", 1)[1].split("def read_credentials():", 1)[0]
        self.assertLess(baseline.index('apply_file("deploy/namespace.yaml")'), baseline.index("validate_baseline()"))
        self.assertLess(baseline.index("validate_baseline()"), baseline.index('apply_secret("postgres-auth"'))
        apply_helper = controller.split("def apply_file(", 1)[1].split("def validate_file(", 1)[0]
        self.assertLess(apply_helper.index('"--dry-run=server"'), apply_helper.index("kctl(*cmd"))
        start = controller.split("def lab_start(", 1)[1].split("def verify_recovery(", 1)[0]
        self.assertIn("apply_file(SCENARIOS[lab][1])", start)
        self.assertIn('"--dry-run=server", "-k"', controller)

    def test_all_scenario_ids_have_fault_assets(self):
        self.assertEqual(set(lab.SCENARIOS), {f"{i:02d}" for i in range(1, 13)})
        for _, path in lab.SCENARIOS.values():
            self.assertTrue((ROOT / path).is_file())

    def test_catalog_titles_and_student_pages_match_controller(self):
        catalog = yaml.safe_load((ROOT / "scenarios/catalog.yaml").read_text())["catalog"]
        self.assertEqual({str(item["id"]) for item in catalog}, set(lab.SCENARIOS))
        for item in catalog:
            title, fault = lab.SCENARIOS[str(item["id"])]
            self.assertEqual(title, item["title"])
            self.assertEqual(fault, item["fault"])
            self.assertTrue((ROOT / item["student"]).is_file())

    def test_lab_suite_covers_catalog_twice_with_unrepaired_negative_control(self):
        catalog = yaml.safe_load((ROOT / "scenarios/catalog.yaml").read_text())["catalog"]
        suite = (ROOT / "scripts/lab_suite.py").read_text()
        main = suite.split("def main():", 1)[1]
        self.assertEqual([str(item["id"]) for item in catalog], [f"{i:02d}" for i in range(1, 13)])
        self.assertTrue(all(item["automated_suite"] == "scripts/lab_suite.py" for item in catalog))
        self.assertIn('IDS = [f"{i:02d}" for i in range(1, 13)]', suite)
        self.assertIn("for attempt in (1, 2):", main)
        self.assertIn("for lab in IDS:", main)
        negative_check = 'run("make", "lab-verify", f"LAB={lab}", expected=1)'
        repaired_check = 'run("make", "lab-verify", f"LAB={lab}")'
        self.assertIn(negative_check, main)
        self.assertLess(main.index(negative_check), main.index("repair(lab)"))
        self.assertLess(main.index("repair(lab)"), main.index(repaired_check))

    def test_local_cluster_names_are_explicit(self):
        self.assertEqual(lab.CLUSTER, "k3s-devops-lab")
        self.assertEqual(lab.CONTEXT, "k3d-k3s-devops-lab")
        self.assertEqual(lab.KUBECONFIG, ROOT / ".lab/kubeconfig")

    def test_blind_capstone_state_view_hides_id_title_and_selected_worker(self):
        private_state = {
            "state": "active", "lab": "12", "title": "Blind worker capstone",
            "worker_node": "k3d-k3s-devops-lab-agent-0", "started_at": "2026-11-25T00:00:00+00:00",
        }
        public = lab.public_state_view(private_state)
        self.assertEqual(public, {"state": "active", "started_at": private_state["started_at"]})
        diagnostics = lab.public_state_view(private_state, ("state", "lab", "title", "started_at"))
        self.assertEqual(diagnostics, {"state": "active", "started_at": private_state["started_at"]})
        ordinary = lab.public_state_view({**private_state, "lab": "03"})
        self.assertEqual(ordinary["lab"], "03")
        self.assertEqual(ordinary["title"], "Blind worker capstone")
        self.assertNotIn("worker_node", ordinary)
        self.assertNotIn("run_id", lab.public_state_view({**private_state, "run_id": "private"}))
        controller = (ROOT / "scripts/lab.py").read_text()
        self.assertIn('json.dumps(public_state_view(read_state()), indent=2)', controller)
        self.assertIn('safe_state = public_state_view(state, ("state", "lab", "title", "started_at", "healthy_at", "last_reset"))', controller)

    def test_public_scenario_catalog_hides_the_blind_capstone_id(self):
        self.assertEqual(lab.public_scenario_label("12", "Blind worker capstone"), "CAPSTONE  Blind worker capstone")
        self.assertEqual(lab.public_scenario_label("03", "Database DNS failure"), "03  Database DNS failure")
        controller = (ROOT / "scripts/lab.py").read_text()
        self.assertIn("say(public_scenario_label(key, title))", controller)

    def test_k3d_compatibility_references_match_the_pinned_release(self):
        techstack = (ROOT / "docs/techstack.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for url in (
            "https://k3d.io/v5.9.0/",
            "https://k3d.io/v5.9.0/usage/configfile/",
            "https://k3d.io/v5.9.0/usage/commands/k3d_cluster_create/",
            "https://k3d.io/v5.9.0/usage/commands/k3d_version/",
        ):
            self.assertIn(url, techstack)
        self.assertIn("https://k3d.io/v5.9.0/", readme)
        self.assertNotIn("https://k3d.io/stable/", techstack)

    def test_kubectl_and_k3d_helpers_use_separate_private_kubeconfigs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            kubeconfig = lab_dir / "kubeconfig"
            kubeconfig.write_text("private lab config")
            k3d_kubeconfig = lab_dir / "k3d-private-kubeconfig"
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "run", return_value=SimpleNamespace(returncode=0)) as run:
                lab.kctl("get", "pods")
                run.assert_called_once()
                kubectl_args = run.call_args.args[0]
                self.assertEqual(kubectl_args[:4], ["kubectl", "--kubeconfig", kubeconfig, "--context"])
                self.assertEqual(kubectl_args[4], lab.CONTEXT)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "K3D_KUBECONFIG", k3d_kubeconfig
            ), patch.object(lab, "run", return_value=SimpleNamespace(returncode=0)) as run:
                lab.k3d_run("cluster", "list", capture=True)
                command = run.call_args.args[0]
                environment = run.call_args.kwargs["env"]
                self.assertEqual(command[:3], ["k3d", "cluster", "list"])
                self.assertEqual(environment["KUBECONFIG"], str(k3d_kubeconfig))
                self.assertNotEqual(environment["KUBECONFIG"], str(kubeconfig))
        cluster_config = yaml.safe_load((ROOT / "cluster/k3d.yaml").read_text())
        self.assertFalse(cluster_config["options"]["kubeconfig"]["updateDefaultKubeconfig"])
        self.assertFalse(cluster_config["options"]["kubeconfig"]["switchCurrentContext"])

    def test_up_refuses_to_reconcile_while_teardown_is_in_progress(self):
        with patch.object(lab, "read_state", return_value={"cluster_created": True, "state": "deleting"}), patch.object(
            lab, "preflight"
        ) as preflight, self.assertRaisesRegex(lab.LabError, "teardown is in progress"):
            lab.up()
        preflight.assert_not_called()

    def test_k3d_cluster_list_rejects_unexpected_json_shapes(self):
        for payload in ("null", "{}", "[null]"):
            with self.subTest(payload=payload), patch.object(
                lab, "k3d_run", return_value=SimpleNamespace(returncode=0, stdout=payload)
            ), self.assertRaisesRegex(lab.LabError, "unexpected JSON structure"):
                lab.listed_clusters()

    def test_partial_creation_identity_requires_private_owner_marker_on_every_node(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            kubeconfig = lab_dir / "kubeconfig"
            kubeconfig.write_text("private")
            owner_file = lab_dir / "owner.json"
            owner_token = "a" * 32
            owner_file.write_text(json.dumps({"token": owner_token}))
            config = {"contexts": [{"name": lab.CONTEXT, "context": {"cluster": f"k3d-{lab.CLUSTER}"}}]}
            nodes = {"items": [{"metadata": {
                "name": f"k3d-{lab.CLUSTER}-server-0",
                "labels": {"lab.k3s-devops.invalid/owner": owner_token},
            }}]}
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "OWNER_FILE", owner_file), patch.object(
                lab, "run", return_value=SimpleNamespace(stdout=json.dumps(config))
            ), patch.object(lab, "kctl", return_value=SimpleNamespace(stdout=json.dumps(nodes))):
                lab.ensure_partial_creation_identity()
            nodes["items"][0]["metadata"]["labels"]["lab.k3s-devops.invalid/owner"] = "b" * 32
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "OWNER_FILE", owner_file), patch.object(
                lab, "run", return_value=SimpleNamespace(stdout=json.dumps(config))
            ), patch.object(lab, "kctl", return_value=SimpleNamespace(stdout=json.dumps(nodes))), self.assertRaises(
                lab.UnsafeTarget
            ):
                lab.ensure_partial_creation_identity()

    def test_unmeasured_resource_estimates_are_advisories(self):
        below = lab.resource_estimate_warnings(2, 8 * 1024**3, 10 * 1024**3)
        self.assertEqual(len(below), 2)
        self.assertEqual(lab.resource_estimate_warnings(8, 24 * 1024**3, 50 * 1024**3), [])

    def test_preflight_version_parsers_and_manifest_pins(self):
        self.assertEqual(lab.parse_k3d_version("k3d version v5.9.0\nk3s version v1.36.6-k3s1 (default)"), "v5.9.0")
        self.assertEqual(lab.parse_kubectl_version(json.dumps({"clientVersion": {"gitVersion": "v1.36.6"}})), "v1.36.6")
        self.assertEqual(lab.parse_docker_version("20.10.5+dfsg1"), (20, 10, 5))
        self.assertEqual(lab.parse_docker_version("29.0.0"), (29, 0, 0))
        with self.assertRaisesRegex(lab.LabError, "could not read k3d version"):
            lab.parse_k3d_version("k3d development build")
        with self.assertRaisesRegex(lab.LabError, "could not read kubectl client version"):
            lab.parse_kubectl_version("{}")
        with self.assertRaisesRegex(lab.LabError, "could not read Docker Engine"):
            lab.parse_docker_version("unknown")
        self.assertEqual(lab.MIN_DOCKER_VERSION, (20, 10, 5))
        pins = yaml.safe_load((ROOT / "versions.yaml").read_text())
        self.assertEqual(lab.PINNED_K3D_VERSION, pins["tools"]["k3d"])
        self.assertEqual(lab.PINNED_KUBECTL_VERSION, pins["tools"]["kubectl"])
        self.assertEqual(pins["tools"]["k3s"], pins["images"]["k3s-node"].rsplit(":", 1)[1])
        self.assertEqual(lab.PINNED_K3S_NODE_VERSION, pins["tools"]["k3s"].replace("-k3s", "+k3s"))
        api_version = re.match(r"python:(\d+\.\d+\.\d+)", pins["images"]["api"])
        self.assertEqual(".".join(map(str, lab.PINNED_PYTHON_VERSION)), api_version.group(1))

    def test_preflight_checks_pinned_cli_versions_before_docker(self):
        controller = (ROOT / "scripts/lab.py").read_text()
        preflight = controller.split("def preflight():", 1)[1].split("def start_cluster(", 1)[0]
        self.assertLess(preflight.index("check_cli_versions()"), preflight.index('["docker", "info"'))

    def test_cluster_identity_enforces_pinned_k3s_nodes_but_teardown_can_remove_stale_version(self):
        names = (
            f"k3d-{lab.CLUSTER}-server-0",
            f"k3d-{lab.CLUSTER}-agent-0",
            f"k3d-{lab.CLUSTER}-agent-1",
        )
        nodes = [{
            "metadata": {"name": name},
            "status": {"nodeInfo": {"kubeletVersion": lab.PINNED_K3S_NODE_VERSION}},
        } for name in names]
        self.assertEqual(lab.validate_cluster_nodes(nodes), nodes)
        stale = json.loads(json.dumps(nodes))
        stale[1]["status"]["nodeInfo"]["kubeletVersion"] = "v1.36.5+k3s1"
        with self.assertRaisesRegex(lab.UnsafeTarget, "pinned K3s version"):
            lab.validate_cluster_nodes(stale)
        self.assertEqual(lab.validate_cluster_nodes(stale, allow_version_mismatch=True), stale)
        with self.assertRaisesRegex(lab.UnsafeTarget, "exactly the three expected lab nodes"):
            lab.validate_cluster_nodes(nodes[:2])
        missing_version = json.loads(json.dumps(nodes))
        del missing_version[0]["status"]
        with self.assertRaisesRegex(lab.UnsafeTarget, "pinned K3s version"):
            lab.validate_cluster_nodes(missing_version)
        self.assertEqual(lab.validate_cluster_nodes(missing_version, allow_version_mismatch=True), missing_version)
        controller = (ROOT / "scripts/lab.py").read_text()
        down = controller.split("def down(", 1)[1].split("def main(", 1)[0]
        self.assertIn("allow_version_mismatch=True", down)

    def test_stale_k3s_teardown_override_keeps_owner_and_namespace_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            kubeconfig = lab_dir / "kubeconfig"
            kubeconfig.write_text("private")
            owner_file = lab_dir / "owner.json"
            token = "c" * 32
            owner_file.write_text(json.dumps({"token": token}))
            config = {"contexts": [{"name": lab.CONTEXT, "context": {"cluster": f"k3d-{lab.CLUSTER}"}}]}
            names = (
                f"k3d-{lab.CLUSTER}-server-0",
                f"k3d-{lab.CLUSTER}-agent-0",
                f"k3d-{lab.CLUSTER}-agent-1",
            )
            nodes = {"items": [{
                "metadata": {
                    "name": name,
                    "labels": {
                        "lab.k3s-devops.invalid/owner": token,
                        **({"lab.k3s-devops.invalid/control-plane": "true"} if "server" in name else {"lab.k3s-devops.invalid/worker": "true"}),
                    },
                },
                "status": {"nodeInfo": {"kubeletVersion": "v1.36.5+k3s1"}},
            } for name in names]}
            namespace = {"metadata": {"labels": {"app.kubernetes.io/part-of": "k3s-devops-lab"}}}
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "OWNER_FILE", owner_file), patch.object(
                lab, "run", return_value=SimpleNamespace(stdout=json.dumps(config))
            ), patch.object(lab, "kctl", side_effect=[
                SimpleNamespace(stdout=json.dumps(nodes)), SimpleNamespace(stdout=json.dumps(namespace), returncode=0)
            ]):
                lab.ensure_identity(allow_version_mismatch=True)

            nodes["items"][1]["metadata"]["labels"]["lab.k3s-devops.invalid/owner"] = "d" * 32
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "OWNER_FILE", owner_file), patch.object(
                lab, "run", return_value=SimpleNamespace(stdout=json.dumps(config))
            ), patch.object(
                lab, "kctl", return_value=SimpleNamespace(stdout=json.dumps(nodes))
            ), self.assertRaisesRegex(lab.UnsafeTarget, "ownership marker"):
                lab.ensure_identity(allow_version_mismatch=True)

    def test_no_known_development_password_is_committed(self):
        forbidden = "lab-local-" + "change-me"
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or ".lab" in path.parts:
                continue
            try: contents = path.read_text()
            except (UnicodeDecodeError, OSError): continue
            self.assertNotIn(forbidden, contents)

    def test_fluent_bit_host_mounts_and_rbac_are_documented_and_scoped(self):
        manifest = list(yaml.safe_load_all((ROOT / "observability/fluent-bit-daemonset.yaml").read_text()))
        role = next(item for item in manifest if item.get("kind") == "ClusterRole")
        self.assertEqual(role["rules"], [{
            "apiGroups": [""],
            "resources": ["namespaces", "pods", "nodes"],
            "verbs": ["get", "list", "watch"],
        }])
        daemonset = next(item for item in manifest if item.get("kind") == "DaemonSet")
        pod_spec = daemonset["spec"]["template"]["spec"]
        mounts = {mount["name"]: mount for mount in pod_spec["containers"][0]["volumeMounts"]}
        volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
        for name, path in (("containers", "/var/log/containers"), ("pods", "/var/log/pods")):
            self.assertEqual(volumes[name]["hostPath"]["path"], path)
            self.assertTrue(mounts[name]["readOnly"])
        self.assertEqual(volumes["state"]["hostPath"]["path"], "/var/lib/fluent-bit")
        self.assertFalse(mounts["state"].get("readOnly", False))
        operations = (ROOT / "observability/README.md").read_text()
        self.assertIn("paths inside the k3d node containers", operations)
        self.assertIn("has no Kubernetes write verbs", operations)

    def test_kibana_dashboard_references_all_trend_charts(self):
        records = [json.loads(line) for line in (ROOT / "observability/kibana-objects.ndjson").read_text().splitlines()]
        expected = {"request-volume-trend", "error-volume-trend", "ingestion-volume-trend"}
        charts = {record["id"] for record in records if record["type"] == "lens"}
        self.assertTrue(expected <= charts)
        dashboard = next(record for record in records if record["type"] == "dashboard" and record["id"] == "orders-incident-dashboard")
        chart_refs = {ref["id"] for ref in dashboard["references"] if ref["type"] == "lens"}
        self.assertTrue(expected <= chart_refs)
        panels = json.loads(dashboard["attributes"]["panelsJSON"])
        reference_names = {ref["name"] for ref in dashboard["references"]}
        self.assertTrue(all(panel["panelRefName"] in reference_names for panel in panels))

    def test_doctor_checks_all_provisioned_kibana_searches(self):
        records = [json.loads(line) for line in (ROOT / "observability/kibana-objects.ndjson").read_text().splitlines()]
        expected = {"api-incident-overview", "failed-orders", "database-timeouts", "ingestion-health"}
        provisioned = {record["id"] for record in records if record["type"] == "search"}
        self.assertTrue(expected <= provisioned)
        controller = (ROOT / "scripts/lab.py").read_text()
        dashboard_check = controller.split("def kibana_dashboard_ready():", 1)[1].split("def grafana_dashboards_ready():", 1)[0]
        self.assertIn("expected_searches", dashboard_check)
        self.assertIn("/api/saved_objects/search/", dashboard_check)

    def test_suite_order_check_queries_the_exact_synthetic_sku(self):
        sku = "SUITE-SENTINEL"
        with patch.object(lab, "ensure_identity"), patch.object(
            lab, "read_state", return_value={"state": "healthy", "lab": None}
        ), patch.object(lab, "suite_api_request", return_value=(200, {"items": [{"sku": sku}]})) as request:
            lab.suite_order_check(sku)
        request.assert_called_once_with("GET", "/orders?sku=SUITE-SENTINEL")

    def test_database_bootstrap_reconciles_role_password_and_fixtures(self):
        bootstrap = (ROOT / "deploy/db-bootstrap.yaml").read_text()
        self.assertIn("ALTER ROLE orders_app WITH LOGIN PASSWORD :'app_password';", bootstrap)
        self.assertIn("ON CONFLICT (fixture_key) DO NOTHING;", bootstrap)
        controller = (ROOT / "scripts/lab.py").read_text()
        baseline = controller.split("def baseline():", 1)[1].split("def read_credentials():", 1)[0]
        delete_job = baseline.index('"delete", "job", "db-bootstrap"')
        apply_job = baseline.index('apply_file("deploy/db-bootstrap.yaml")')
        wait_job = baseline.index('"job/db-bootstrap"')
        self.assertLess(delete_job, apply_job)
        self.assertLess(apply_job, wait_job)
        up = controller.split("def up():", 1)[1].split("def detect(", 1)[0]
        self.assertLess(up.index("read_credentials()"), up.index("start_cluster()"))

    def test_missing_credentials_fail_closed_for_recorded_cluster(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            state_path = lab_dir / "state.json"
            state_path.write_text(json.dumps({"cluster_created": True, "state": "healthy"}))
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "STATE_FILE", state_path
            ):
                with self.assertRaisesRegex(lab.LabError, "credentials are missing"):
                    lab.read_credentials()
            self.assertFalse((lab_dir / "credentials.json").exists())

    def test_lifecycle_state_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            state_path = lab_dir / "state.json"
            for contents in ("[]", "null", '"healthy"'):
                state_path.write_text(contents)
                with self.subTest(contents=contents), patch.object(lab, "ROOT", root), patch.object(
                    lab, "LAB_DIR", lab_dir
                ), patch.object(lab, "STATE_FILE", state_path), self.assertRaisesRegex(
                    lab.LabError, "expected a JSON object"
                ):
                    lab.read_state()

    def test_missing_credentials_are_created_for_a_fresh_lab(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            state_path = lab_dir / "state.json"
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "STATE_FILE", state_path
            ):
                credentials = lab.read_credentials()
            self.assertEqual(set(credentials), {"postgres", "app", "grafana"})
            self.assertTrue(all(credentials.values()))
            self.assertEqual(stat.S_IMODE((lab_dir / "credentials.json").stat().st_mode), 0o600)

    def test_malformed_credentials_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            credentials_path = lab_dir / "credentials.json"
            credentials_path.write_text("null")
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir):
                with self.assertRaisesRegex(lab.LabError, "incomplete or invalid"):
                    lab.read_credentials()
            self.assertEqual(credentials_path.read_text(), "null")

    def test_teardown_cleanup_preserves_unmanaged_lab_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            (lab_dir / "state.json").write_text("managed")
            (lab_dir / "diagnostics-20261125T120000Z.json").write_text("managed")
            (lab_dir / "my-notes.txt").write_text("user data")
            (lab_dir / "custom").mkdir()
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir):
                lab.cleanup_lab_files()
            self.assertFalse((lab_dir / "state.json").exists())
            self.assertFalse((lab_dir / "diagnostics-20261125T120000Z.json").exists())
            self.assertEqual((lab_dir / "my-notes.txt").read_text(), "user data")
            self.assertTrue((lab_dir / "custom").is_dir())

    def test_teardown_cleans_local_state_after_interrupted_empty_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            state_path = lab_dir / "state.json"
            state_path.write_text(json.dumps({"cluster_owned_intent": True, "cluster_created": False, "state": "cluster_creating"}))
            (lab_dir / "owner.json").write_text(json.dumps({"token": "a" * 32}))
            (lab_dir / "notes.txt").write_text("keep")
            listing = SimpleNamespace(stdout="[]", returncode=0)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "STATE_FILE", state_path
            ), patch.object(lab, "LOCK_FILE", lab_dir / "lock"), patch.object(
                lab, "k3d_run", return_value=listing
            ):
                lab.down(confirmed=True)
            self.assertEqual(json.loads(state_path.read_text())["state"], "absent")
            self.assertFalse((lab_dir / "owner.json").exists())
            self.assertEqual((lab_dir / "notes.txt").read_text(), "keep")

    def test_teardown_retry_revalidates_identity_when_namespace_is_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            kubeconfig = lab_dir / "kubeconfig"
            kubeconfig.write_text("private")
            state_path = lab_dir / "state.json"
            state_path.write_text(json.dumps({"cluster_created": True, "state": "deleting", "lab": None}))
            listing = SimpleNamespace(stdout=json.dumps([{"name": lab.CLUSTER}]), returncode=0)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir), patch.object(
                lab, "STATE_FILE", state_path
            ), patch.object(lab, "LOCK_FILE", lab_dir / "lock"), patch.object(
                lab, "KUBECONFIG", kubeconfig
            ), patch.object(lab, "k3d_run", return_value=listing), patch.object(
                lab, "ensure_identity"
            ) as identify:
                lab.down(confirmed=True)
            identify.assert_called_once_with(allow_bootstrap=True)

    def test_lab_state_directory_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            external = Path(temporary) / "external"
            root.mkdir()
            external.mkdir()
            (root / ".lab").symlink_to(external, target_is_directory=True)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", root / ".lab"):
                with self.assertRaises(lab.UnsafeTarget):
                    lab.ensure_lab_dir()

    def test_private_lab_files_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir()
            outside = root / "outside"
            outside.write_text("outside")
            (lab_dir / "kubeconfig").symlink_to(outside)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir):
                with self.assertRaises(lab.UnsafeTarget):
                    lab.ensure_lab_file(lab_dir / "kubeconfig")

    def test_private_lab_permissions_are_restricted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lab_dir = root / ".lab"
            lab_dir.mkdir(mode=0o755)
            private_file = lab_dir / "credentials.json"
            private_file.write_text("{}")
            private_file.chmod(0o644)
            with patch.object(lab, "ROOT", root), patch.object(lab, "LAB_DIR", lab_dir):
                lab.ensure_lab_file(private_file)
            self.assertEqual(stat.S_IMODE(lab_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(private_file.stat().st_mode), 0o600)

    def test_recovery_requires_two_ready_pods_and_service_endpoints(self):
        deployment = {"spec": {"replicas": 2}, "status": {"readyReplicas": 2, "availableReplicas": 2}}
        pods = {"items": [
            {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ]}
        endpoint_slices = {"items": [{"endpoints": [
            {"addresses": ["10.0.0.1"], "conditions": {"ready": True}},
            {"addresses": ["10.0.0.2"], "conditions": {"ready": True}},
        ]}]}
        service = {"spec": {"selector": {"app.kubernetes.io/name": "orders-api"}}}
        outputs = [json.dumps(service), json.dumps(pods), json.dumps(endpoint_slices)]
        with patch.object(lab, "deployment_object", return_value=deployment), patch.object(
            lab, "kctl", side_effect=[SimpleNamespace(stdout=value) for value in outputs]
        ):
            self.assertTrue(lab.api_baseline_ready())

        endpoint_slices["items"][0]["endpoints"].pop()
        cases = (
            ({"spec": {"replicas": 1}, "status": {"readyReplicas": 2, "availableReplicas": 2}}, pods, endpoint_slices),
            (deployment, {"items": pods["items"][:1]}, endpoint_slices),
            (deployment, pods, endpoint_slices),
        )
        for case_deployment, case_pods, case_slices in cases:
            with self.subTest(deployment=case_deployment["spec"], pod_count=len(case_pods["items"])):
                outputs = [json.dumps(service), json.dumps(case_pods), json.dumps(case_slices)]
                with patch.object(lab, "deployment_object", return_value=case_deployment), patch.object(
                    lab, "kctl", side_effect=[SimpleNamespace(stdout=value) for value in outputs]
                ):
                    self.assertFalse(lab.api_baseline_ready())

    def test_worker_capstone_requires_scheduling_impact(self):
        node = {"spec": {"unschedulable": True}}
        deployment = {"spec": {"replicas": 2}, "status": {"readyReplicas": 1}}
        pods = [
            {"metadata": {"labels": {"app.kubernetes.io/name": "orders-api"}}, "status": {"phase": "Running"}},
            {"metadata": {"labels": {"app.kubernetes.io/name": "orders-api"}}, "status": {"phase": "Pending"}},
        ]
        self.assertTrue(lab.worker_fault_observed(node, deployment, pods))
        self.assertFalse(lab.worker_fault_observed(node, {"spec": {"replicas": 2}, "status": {"readyReplicas": 2}}, pods))
        self.assertFalse(lab.worker_fault_observed({"spec": {"unschedulable": False}}, deployment, pods))
        self.assertFalse(lab.worker_fault_observed(node, deployment, pods[:1]))

    def test_version_fault_evidence_matches_request_version_error_and_status(self):
        request_id = "a" * 32
        document = {
            "http.request.id": request_id,
            "service.version": "v2",
            "error.type": "synthetic_failure",
            "http.response.status_code": 503,
        }
        with patch.object(lab, "elastic_request_documents", return_value=[document]):
            self.assertTrue(lab.indexed_version_failure(request_id, "v2"))
            self.assertFalse(lab.indexed_version_failure(request_id, "v1"))
        for key, value in (("http.request.id", "b" * 32), ("error.type", "db_connection_error"), ("http.response.status_code", 200)):
            altered = {**document, key: value}
            with patch.object(lab, "elastic_request_documents", return_value=[altered]):
                self.assertFalse(lab.indexed_version_failure(request_id, "v2"))

    def test_ingress_fault_requires_healthy_direct_service_control(self):
        self.assertTrue(lab.ingress_host_fault_observed(["wrong.lab.test"], 404, 200))
        self.assertFalse(lab.ingress_host_fault_observed(["wrong.lab.test"], 404, 503))
        self.assertFalse(lab.ingress_host_fault_observed(["orders.lab.test"], 404, 200))
        self.assertFalse(lab.ingress_host_fault_observed(["wrong.lab.test"], 200, 200))
        baseline = {
            "rules": [{"host": "orders.lab.test", "http": {"paths": [{
                "path": "/", "pathType": "Prefix",
                "backend": {"service": {"name": "orders-api", "port": {"number": 80}}},
            }]}}],
        }
        self.assertTrue(lab.ingress_baseline_restored(baseline))
        self.assertFalse(lab.ingress_baseline_restored({**baseline, "rules": [
            *baseline["rules"], {"host": "wrong.lab.test"}
        ]}))

    def test_service_selector_fault_requires_exact_selector_and_ready_pods(self):
        selector = {"app.kubernetes.io/name": "deliberately-absent"}
        self.assertTrue(lab.service_selector_fault_observed(selector, 2, 0))
        self.assertFalse(lab.service_selector_fault_observed({"app": "missing"}, 2, 0))
        self.assertFalse(lab.service_selector_fault_observed(selector, 1, 0))
        self.assertFalse(lab.service_selector_fault_observed(selector, 2, 1))
        self.assertTrue(lab.api_service_selector_baseline({"app.kubernetes.io/name": "orders-api"}))
        self.assertFalse(lab.api_service_selector_baseline(selector))

    def test_latency_fault_requires_injected_delay_and_successful_slow_request(self):
        self.assertTrue(lab.latency_fault_observed("0.8", 200, .8))
        self.assertFalse(lab.latency_fault_observed("0", 200, .8))
        self.assertFalse(lab.latency_fault_observed("0.8", 503, .8))
        self.assertFalse(lab.latency_fault_observed("0.8", 200, .2))

    def test_memory_fault_requires_configured_limit_and_oom_evidence(self):
        pods = [{"status": {"containerStatuses": [{"lastState": {"terminated": {"reason": "OOMKilled"}}}]}}]
        self.assertTrue(lab.memory_fault_observed("512", "128Mi", pods))
        self.assertFalse(lab.memory_fault_observed("0", "128Mi", pods))
        self.assertFalse(lab.memory_fault_observed("512", "1Gi", pods))
        self.assertFalse(lab.memory_fault_observed("512", "128Mi", []))
        self.assertTrue(lab.memory_baseline_restored(None, "256Mi"))
        self.assertFalse(lab.memory_baseline_restored("512", "256Mi"))
        self.assertFalse(lab.memory_baseline_restored("0", "256Mi"))
        self.assertFalse(lab.memory_baseline_restored(None, "128Mi"))

    def test_latency_and_worker_placement_recovery_require_exact_baseline(self):
        self.assertTrue(lab.latency_baseline_restored(None))
        self.assertFalse(lab.latency_baseline_restored("-0.1"))
        self.assertTrue(lab.api_worker_selector_baseline({"lab.k3s-devops.invalid/worker": "true"}))
        self.assertFalse(lab.api_worker_selector_baseline({"lab.k3s-devops.invalid/worker": "true", "zone": "lab"}))

    def test_logging_and_metrics_faults_require_the_scenario_config(self):
        self.assertTrue(lab.logging_fault_configured("[OUTPUT]\nName stdout\n"))
        self.assertFalse(lab.logging_fault_configured("[OUTPUT]\nName es\n"))
        self.assertTrue(lab.logging_baseline_configured("[OUTPUT]\nName es\n"))
        self.assertFalse(lab.logging_baseline_configured("[OUTPUT]\nName es\nName stdout\n"))
        fault = {"prometheus.io/scrape": "true", "prometheus.io/path": "/missing-metrics", "prometheus.io/port": "8000"}
        self.assertTrue(lab.metrics_fault_configured(fault))
        self.assertFalse(lab.metrics_fault_configured({**fault, "prometheus.io/path": "/metrics"}))
        self.assertFalse(lab.metrics_fault_configured({**fault, "prometheus.io/port": "9090"}))
        baseline = {"prometheus.io/scrape": "true", "prometheus.io/path": "/metrics", "prometheus.io/port": "8000"}
        self.assertTrue(lab.metrics_baseline_configured(baseline))
        self.assertFalse(lab.metrics_baseline_configured({**baseline, "prometheus.io/path": "/missing-metrics"}))

    def test_readiness_fault_requires_wrong_probe_and_healthy_old_replicas(self):
        pods = [
            {"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}},
            {"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}]}},
        ]
        self.assertTrue(lab.readiness_fault_observed("/wrong-ready-path", pods, True, 200))
        self.assertFalse(lab.readiness_fault_observed("/readyz", pods, True, 200))
        self.assertFalse(lab.readiness_fault_observed("/wrong-ready-path", pods, False, 200))
        self.assertFalse(lab.readiness_fault_observed("/wrong-ready-path", pods, True, 503))

    def test_scheduling_fault_requires_expected_selector_and_pending_replacement(self):
        selector = {"lab.k3s-devops.invalid/worker": "nowhere"}
        pods = [{"status": {"phase": "Pending"}}]
        self.assertTrue(lab.scheduling_fault_observed(selector, pods, True, 200))
        self.assertFalse(lab.scheduling_fault_observed({}, pods, True, 200))
        self.assertFalse(lab.scheduling_fault_observed(selector, [], True, 200))
        self.assertFalse(lab.scheduling_fault_observed(selector, pods, False, 200))

    def test_pool_fault_evidence_requires_timeout_error(self):
        request_id = "c" * 32
        document = {
            "http.request.id": request_id,
            "service.version": "v1",
            "error.type": "db_pool_timeout",
            "http.response.status_code": 503,
        }
        with patch.object(lab, "elastic_request_documents", return_value=[document]):
            self.assertTrue(lab.indexed_request_error(request_id, "db_pool_timeout"))
            self.assertFalse(lab.indexed_request_error(request_id, "db_connection_error"))
        wrong_status = {**document, "http.response.status_code": 200}
        with patch.object(lab, "elastic_request_documents", return_value=[wrong_status]):
            self.assertFalse(lab.indexed_request_error(request_id, "db_pool_timeout"))

    def test_database_dns_scenario_requires_a_ready_postgres_negative_control(self):
        ready = [{"status": {"conditions": [{"type": "Ready", "status": "True"}]}}]
        self.assertTrue(lab.postgres_pods_ready(ready))
        self.assertFalse(lab.postgres_pods_ready([]))
        self.assertFalse(lab.postgres_pods_ready([{"status": {"conditions": [{"type": "Ready", "status": "False"}]}}]))
        self.assertFalse(lab.postgres_pods_ready([*ready, *ready]))
        controller = (ROOT / "scripts/lab.py").read_text()
        detector = controller.split("def detect(lab):", 1)[1].split("def lab_start(", 1)[0]
        dns_scenario = detector.split('if lab == "03":', 1)[1].split("\n    if lab == ", 1)[0]
        self.assertIn("postgres_pods_ready(postgres_pods)", dns_scenario)

    def test_observability_fault_detectors_require_negative_controls(self):
        controller = (ROOT / "scripts/lab.py").read_text()
        detector = controller.split("def detect(lab):", 1)[1].split("def lab_start(", 1)[0]
        self.assertIn("service_selector_fault_observed(", detector)
        self.assertIn("readiness_fault_observed(", detector)
        self.assertIn("scheduling_fault_observed(", detector)
        self.assertIn('if http_probe("/livez")[0] != 200: return False', detector)
        self.assertIn('indexed_request_error(request_id, "db_dns_error")', detector)
        self.assertIn('deployment_env("DB_HOST") != "postgres-missing.lab.svc.cluster.local"', detector)
        self.assertIn('deployment_env("FAULT_FAIL_PERCENT") != "35"', detector)
        self.assertIn("ingress_host_fault_observed(", detector)
        self.assertIn("latency_fault_observed(", detector)
        self.assertIn("memory_fault_observed(", detector)
        self.assertIn("logging_fault_configured(", detector)
        self.assertIn("metrics_fault_configured(", detector)
        self.assertIn("if not elastic_search_ready(): return False", detector)
        self.assertIn("return elastic_has_request(request_id)", detector)
        health = controller.split("def elastic_search_ready():", 1)[1].split("def indexed_request_error(", 1)[0]
        self.assertIn('"/_cluster/health"', health)

    def test_recovery_requires_fault_configuration_to_be_restored(self):
        controller = (ROOT / "scripts/lab.py").read_text()
        baseline = controller.split("def api_baseline_ready():", 1)[1].split("def api_restart_snapshot(", 1)[0]
        verifier = controller.split("def verify_recovery(lab):", 1)[1].split("def lab_verify(", 1)[0]
        self.assertIn("api_service_selector_baseline(", baseline)
        self.assertIn('deployment_env("DB_HOST") != "postgres.lab.svc.cluster.local"', verifier)
        self.assertIn('deployment_env("FAULT_FAIL_PERCENT") is not None', verifier)
        self.assertIn("latency_baseline_restored(", verifier)
        self.assertIn('deployment_env("DB_POOL_MAX") != "5"', verifier)
        self.assertIn('deployment_env("DB_HOLD_SECONDS") is not None', verifier)
        self.assertIn("api_worker_selector_baseline(", verifier)
        self.assertIn("memory_baseline_restored(", verifier)
        self.assertIn("logging_baseline_configured(", verifier)
        self.assertIn("metrics_baseline_configured(", verifier)
        for lab_id in ("03", "06", "07"):
            branch = verifier.split(f'if lab == "{lab_id}":', 1)[1].split("\n    if lab == ", 1)[0]
            self.assertIn('"rollout", "status", "deployment/orders-api"', branch)
            self.assertIn("api_baseline_ready()", branch)
        logging_recovery = verifier.split('if lab == "10":', 1)[1].split("\n    if lab == ", 1)[0]
        self.assertIn('"rollout", "status", "daemonset/fluent-bit"', logging_recovery)
        capstone = verifier.split('if lab == "12":', 1)[1]
        self.assertIn('"rollout", "status", "deployment/orders-api"', capstone)
        detector = controller.split("def detect(lab):", 1)[1].split("def lab_start(", 1)[0]
        capstone_detection = detector.split('if lab == "12":', 1)[1]
        self.assertNotIn('"rollout", "status", "deployment/orders-api"', capstone_detection)

    def test_worker_candidate_requires_ready_replicas_on_separate_agents(self):
        nodes = {"items": [
            {"metadata": {"name": f"k3d-{lab.CLUSTER}-agent-0", "labels": {"lab.k3s-devops.invalid/worker": "true"}},
             "spec": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            {"metadata": {"name": f"k3d-{lab.CLUSTER}-agent-1", "labels": {"lab.k3s-devops.invalid/worker": "true"}},
             "spec": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ]}
        pods = {"items": [
            {"metadata": {"labels": {"app.kubernetes.io/name": "orders-api"}},
             "spec": {"nodeName": f"k3d-{lab.CLUSTER}-agent-0"},
             "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            {"metadata": {"labels": {"app.kubernetes.io/name": "orders-api"}},
             "spec": {"nodeName": f"k3d-{lab.CLUSTER}-agent-1"},
             "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ]}
        baseline = {"spec": {"replicas": 2, "template": {"spec": {"nodeSelector": {"lab.k3s-devops.invalid/worker": "true"}}}}}
        outputs = [json.dumps(nodes), json.dumps(pods)]
        with patch.object(lab, "deployment_object", return_value=baseline), patch.object(
            lab, "kctl", side_effect=[SimpleNamespace(stdout=value) for value in outputs]
        ):
            self.assertIn(lab.worker_candidate(), {item["metadata"]["name"] for item in nodes["items"]})

        pods["items"][1]["spec"]["nodeName"] = f"k3d-{lab.CLUSTER}-agent-0"
        outputs = [json.dumps(nodes), json.dumps(pods)]
        with patch.object(lab, "deployment_object", return_value=baseline), patch.object(
            lab, "kctl", side_effect=[SimpleNamespace(stdout=value) for value in outputs]
        ):
            with self.assertRaisesRegex(lab.LabError, "spread across both lab workers"):
                lab.worker_candidate()

        pods["items"][1]["spec"]["nodeName"] = f"k3d-{lab.CLUSTER}-agent-1"
        for deployment in (
            {"spec": {"replicas": 3, "template": {"spec": {"nodeSelector": {"lab.k3s-devops.invalid/worker": "true"}}}}},
            {"spec": {"replicas": 2, "template": {"spec": {"nodeSelector": {"lab.k3s-devops.invalid/worker": "missing"}}}}},
        ):
            outputs = [json.dumps(nodes), json.dumps(pods)]
            with patch.object(lab, "deployment_object", return_value=deployment), patch.object(
                lab, "kctl", side_effect=[SimpleNamespace(stdout=value) for value in outputs]
            ), self.assertRaisesRegex(lab.LabError, "two-replica worker baseline"):
                lab.worker_candidate()

    def test_capstone_checks_api_baseline_before_cordoning_worker(self):
        controller = (ROOT / "scripts/lab.py").read_text()
        start = controller.split("def lab_start(", 1)[1].split("def verify_recovery(", 1)[0]
        capstone = start.split('if lab == "12":', 1)[1].split("else:", 1)[0]
        self.assertLess(capstone.index("api_baseline_ready()"), capstone.index("worker_candidate()"))
        self.assertLess(capstone.index('http_probe("/livez")'), capstone.index("worker_candidate()"))
        self.assertLess(capstone.index('http_probe("/orders")'), capstone.index("worker_candidate()"))
        self.assertLess(capstone.index("worker_candidate()"), capstone.index('kctl("cordon"'))
        candidate = controller.split("def worker_candidate():", 1)[1].split("def worker_fault_observed(", 1)[0]
        self.assertIn('deployment_spec.get("replicas") != 2', candidate)
        self.assertIn("placed != agent_names", candidate)
