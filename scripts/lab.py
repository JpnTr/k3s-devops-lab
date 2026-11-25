#!/usr/bin/env python3
"""K3s DevOps Lab controller. All Kubernetes calls use the private .lab kubeconfig."""
from __future__ import annotations
import argparse, contextlib, fcntl, json, os, re, secrets, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
import base64
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = ROOT / ".lab"
KUBECONFIG = LAB_DIR / "kubeconfig"
K3D_KUBECONFIG = LAB_DIR / "k3d-private-kubeconfig"
OWNER_FILE = LAB_DIR / "owner.json"
STATE_FILE = LAB_DIR / "state.json"
LOCK_FILE = LAB_DIR / "lock"
MANAGED_LAB_FILES = {
    "kubeconfig", "k3d-private-kubeconfig", "owner.json", "state.json",
    "credentials.json",
}
CLUSTER = "k3s-devops-lab"
CONTEXT = "k3d-k3s-devops-lab"
HOST = "127.0.0.1"
PINNED_K3D_VERSION = "v5.9.0"
PINNED_KUBECTL_VERSION = "v1.36.6"
PINNED_K3S_NODE_VERSION = "v1.36.6+k3s1"
PINNED_PYTHON_VERSION = (3, 14, 10)
MIN_DOCKER_VERSION = (20, 10, 5)
SCENARIOS = {
    "01": ("Service has no endpoints", "scenarios/01-service.yaml"),
    "02": ("Readiness path mismatch", "scenarios/02-readiness.yaml"),
    "03": ("Database DNS failure", "scenarios/03-dns.yaml"),
    "04": ("Ingress host mismatch", "scenarios/04-ingress.yaml"),
    "05": ("Faulty API version", "scenarios/05-faulty-version.yaml"),
    "06": ("Slow GET requests", "scenarios/06-latency.yaml"),
    "07": ("Database pool saturation", "scenarios/07-pool.yaml"),
    "08": ("API memory pressure", "scenarios/08-memory.yaml"),
    "09": ("Unschedulable API rollout", "scenarios/09-scheduling.yaml"),
    "10": ("Log collection stopped", "scenarios/10-logging.yaml"),
    "11": ("Metrics scrape failure", "scenarios/11-metrics.yaml"),
    "12": ("Blind worker capstone", "scenarios/12-worker.yaml"),
}

class LabError(Exception): pass
class UnsafeTarget(LabError): pass

def ensure_lab_dir(create=False):
    if LAB_DIR.is_symlink():
        raise UnsafeTarget(".lab must be a real directory, not a symlink")
    if LAB_DIR.exists() and not LAB_DIR.is_dir():
        raise UnsafeTarget(".lab exists but is not a directory")
    if create:
        LAB_DIR.mkdir(mode=0o700, exist_ok=True)
    if LAB_DIR.exists() and LAB_DIR.resolve().parent != ROOT.resolve():
        raise UnsafeTarget(".lab resolves outside the repository root")
    if LAB_DIR.exists():
        os.chmod(LAB_DIR, 0o700)

def ensure_lab_file(path, *, required=False):
    ensure_lab_dir()
    if path.parent != LAB_DIR:
        raise UnsafeTarget("private lab files must be direct children of .lab")
    if path.is_symlink():
        raise UnsafeTarget(f"private lab file {path.name} must not be a symlink")
    if path.exists() and not path.is_file():
        raise UnsafeTarget(f"private lab path {path.name} is not a regular file")
    if path.is_file():
        os.chmod(path, 0o600)
    if required and not path.is_file():
        raise LabError(f"private lab file is missing: {path.name}")

def cleanup_lab_files():
    ensure_lab_dir()
    for path in LAB_DIR.iterdir():
        generated_diagnostic = re.fullmatch(r"diagnostics-\d{8}T\d{6}Z\.json", path.name)
        generated_temporary = re.fullmatch(r"(?:\.state-[A-Za-z0-9_]{8}|secret-[A-Za-z0-9_]{8}\.json)", path.name)
        if path.name not in MANAGED_LAB_FILES and not generated_diagnostic and not generated_temporary:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        path.unlink()

def utc(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def say(message): print(message, flush=True)
def fail(message, status=1):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(status)

def run(args, *, timeout=60, capture=False, env=None, check=True):
    try:
        p = subprocess.run([str(x) for x in args], cwd=ROOT, timeout=timeout, check=False,
                           text=True, stdout=subprocess.PIPE if capture else None,
                           stderr=subprocess.PIPE if capture else None, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise LabError(f"{args[0]} failed or timed out: {type(e).__name__}") from e
    if check and p.returncode:
        detail = (p.stderr or p.stdout or "").strip()[-1200:] if capture else f"exit {p.returncode}"
        raise LabError(f"command failed ({args[0]}): {detail}")
    return p

def atomic_json(path, value):
    ensure_lab_dir(create=True)
    ensure_lab_file(path)
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=path.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(tmp)

def read_state():
    ensure_lab_file(STATE_FILE)
    try:
        state = json.loads(STATE_FILE.read_text())
    except FileNotFoundError: return {"state": "absent"}
    except (OSError, UnicodeError, json.JSONDecodeError) as e: raise LabError(f"lifecycle state is unreadable: {e}")
    if not isinstance(state, dict):
        raise LabError("lifecycle state is unreadable: expected a JSON object")
    return state

def public_state_view(state, keys=None):
    selected = ("cluster_created", "state", "lab", "title", "started_at", "healthy_at", "last_reset", "deleted_at") if keys is None else keys
    view = {key: state[key] for key in selected if key in state}
    # The blind worker capstone keeps its ID, title, and selected worker private
    # until the instructor reveals the verification command.
    if state.get("lab") == "12":
        for key in ("lab", "title", "worker_node"):
            view.pop(key, None)
    return view

def public_scenario_label(lab_id, title):
    return f"CAPSTONE  {title}" if lab_id == "12" else f"{lab_id}  {title}"

@contextlib.contextmanager
def mutation_lock():
    ensure_lab_dir(create=True)
    ensure_lab_file(LOCK_FILE)
    with LOCK_FILE.open("a+") as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise LabError("another lab mutation is in progress")
        yield

def kctl(*args, timeout=60, capture=False, check=True):
    ensure_lab_file(KUBECONFIG, required=True)
    return run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, *args], timeout=timeout, capture=capture, check=check)

def k3d_run(*args, **kwargs):
    # Isolate every k3d kubeconfig operation from the caller's default file.
    ensure_lab_dir(create=True)
    ensure_lab_file(K3D_KUBECONFIG)
    env = os.environ.copy()
    env["KUBECONFIG"] = str(K3D_KUBECONFIG)
    return run(["k3d", *args], env=env, **kwargs)

def validate_cluster_nodes(nodes, *, allow_version_mismatch=False):
    expected_names = {
        f"k3d-{CLUSTER}-server-0",
        f"k3d-{CLUSTER}-agent-0",
        f"k3d-{CLUSTER}-agent-1",
    }
    if not isinstance(nodes, list) or len(nodes) != len(expected_names) or any(
        not isinstance(node, dict)
        or not isinstance(node.get("metadata"), dict)
        or node["metadata"].get("name") not in expected_names
        for node in nodes
    ) or {node["metadata"]["name"] for node in nodes} != expected_names:
        raise UnsafeTarget("cluster does not contain exactly the three expected lab nodes")
    mismatches = [
        (
            node["metadata"]["name"],
            node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion")
            if isinstance(node.get("status"), dict) and isinstance(node["status"].get("nodeInfo"), dict)
            else None,
        )
        for node in nodes
        if not isinstance(node.get("status"), dict)
        or not isinstance(node["status"].get("nodeInfo"), dict)
        or node["status"]["nodeInfo"].get("kubeletVersion") != PINNED_K3S_NODE_VERSION
    ]
    if mismatches and not allow_version_mismatch:
        raise UnsafeTarget(f"cluster node version does not match pinned K3s version {PINNED_K3S_NODE_VERSION}: {mismatches}")
    return nodes

def ensure_identity(allow_bootstrap=False, allow_version_mismatch=False):
    ensure_lab_file(KUBECONFIG, required=True)
    ensure_lab_file(OWNER_FILE, required=True)
    info = run(["kubectl", "--kubeconfig", KUBECONFIG, "config", "view", f"--context={CONTEXT}", "-o", "json"], capture=True)
    cfg = json.loads(info.stdout)
    ctx = next((c for c in cfg.get("contexts", []) if c["name"] == CONTEXT), None)
    if not ctx or ctx["context"].get("cluster") != f"k3d-{CLUSTER}":
        raise UnsafeTarget("kubeconfig does not identify the dedicated k3d context")
    nodes = json.loads(kctl("get", "nodes", "-o", "json", capture=True).stdout).get("items", [])
    validate_cluster_nodes(nodes, allow_version_mismatch=allow_version_mismatch)
    prefix = f"k3d-{CLUSTER}-agent-"
    agents = [n for n in nodes if n.get("metadata", {}).get("name", "").startswith(prefix)
              and n.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/worker") == "true"]
    if len(agents) != 2: raise UnsafeTarget("cluster does not have the two labeled lab agents")
    server = next((n for n in nodes if n.get("metadata", {}).get("name") == f"k3d-{CLUSTER}-server-0"), None)
    if not server or server.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/control-plane") != "true":
        raise UnsafeTarget("cluster does not have the expected labeled lab server")
    try:
        owner = json.loads(OWNER_FILE.read_text())
        owner_token = owner["token"] if isinstance(owner, dict) else None
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e: raise UnsafeTarget("private lab ownership marker is missing or unreadable") from e
    if not isinstance(owner_token, str) or len(owner_token) != 32:
        raise UnsafeTarget("private lab ownership marker is malformed")
    for node in [server, *agents]:
        if node.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/owner") != owner_token:
            raise UnsafeTarget("cluster nodes do not match the private lab ownership marker")
    p = kctl("get", "namespace", "lab", "-o", "json", capture=True, check=False)
    if p.returncode:
        if allow_bootstrap: return
        raise UnsafeTarget("lab namespace identity marker is absent; refusing mutations")
    labels = json.loads(p.stdout).get("metadata", {}).get("labels", {})
    if labels.get("app.kubernetes.io/part-of") != "k3s-devops-lab":
        raise UnsafeTarget("cluster identity marker is absent; refusing all cluster mutations")

def ensure_partial_creation_identity():
    """Prove ownership of an incomplete cluster before startup cleanup."""
    ensure_lab_file(KUBECONFIG, required=True)
    ensure_lab_file(OWNER_FILE, required=True)
    info = run(["kubectl", "--kubeconfig", KUBECONFIG, "config", "view", f"--context={CONTEXT}", "-o", "json"], capture=True)
    cfg = json.loads(info.stdout)
    if not isinstance(cfg, dict):
        raise UnsafeTarget("partial cluster kubeconfig returned an unexpected structure")
    ctx = next((c for c in cfg.get("contexts", []) if isinstance(c, dict) and c.get("name") == CONTEXT), None)
    context = ctx.get("context") if isinstance(ctx, dict) else None
    if not isinstance(context, dict) or context.get("cluster") != f"k3d-{CLUSTER}":
        raise UnsafeTarget("partial cluster kubeconfig does not identify the dedicated lab")
    try:
        owner = json.loads(OWNER_FILE.read_text())
        owner_token = owner["token"] if isinstance(owner, dict) else None
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise UnsafeTarget("partial cluster ownership marker is missing or unreadable") from e
    if not isinstance(owner_token, str) or len(owner_token) != 32:
        raise UnsafeTarget("partial cluster ownership marker is malformed")
    node_document = json.loads(kctl("get", "nodes", "-o", "json", capture=True).stdout)
    nodes = node_document.get("items") if isinstance(node_document, dict) else None
    expected_names = {
        f"k3d-{CLUSTER}-server-0",
        f"k3d-{CLUSTER}-agent-0",
        f"k3d-{CLUSTER}-agent-1",
    }
    if not isinstance(nodes, list) or not nodes or any(
        not isinstance(node, dict)
        or not isinstance(node.get("metadata"), dict)
        or node["metadata"].get("name") not in expected_names
        for node in nodes
    ):
        raise UnsafeTarget("partial cluster contains no provable nodes or an unexpected node")
    if any(
        not isinstance(node["metadata"].get("labels"), dict)
        or node["metadata"]["labels"].get("lab.k3s-devops.invalid/owner") != owner_token
        for node in nodes
    ):
        raise UnsafeTarget("partial cluster nodes do not match the private owner marker")

def wait_rollout(name, namespace="lab", timeout="180s"):
    kind = "statefulset" if name == "elasticsearch" else "deployment"
    kctl("-n", namespace, "rollout", "status", f"{kind}/{name}", f"--timeout={timeout}", timeout=310)

def apply_file(path, namespace=None):
    cmd = ["apply", "-f", ROOT / path]
    if namespace: cmd += ["-n", namespace]
    validation = ["apply", "--dry-run=server", "-f", ROOT / path]
    if namespace: validation += ["-n", namespace]
    kctl(*validation, timeout=90)
    kctl(*cmd, timeout=90)

def validate_file(path):
    """Ask the dedicated cluster API to validate without persisting a manifest."""
    kctl("apply", "--dry-run=server", "-f", ROOT / path, timeout=90)

def validate_baseline():
    # The lab namespace is created before this read-only schema/admission pass.
    for path in (
        "deploy/namespace.yaml",
        "deploy/postgres.yaml",
        "deploy/db-bootstrap.yaml",
        "deploy/api.yaml",
        "deploy/ingress.yaml",
        "app/traffic-deployment.yaml",
    ):
        validate_file(path)
    kctl("apply", "--dry-run=server", "-k", ROOT / "observability", timeout=120)

def apply_secret(name, namespace, fields):
    obj = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": namespace}, "type": "Opaque",
           "data": {k: base64.b64encode(v.encode()).decode() for k, v in fields.items()}}
    fd, tmp = tempfile.mkstemp(prefix="secret-", suffix=".json", dir=LAB_DIR)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f: json.dump(obj, f)
        kctl("apply", "--dry-run=server", "-f", tmp, timeout=30)
        kctl("apply", "-f", tmp, timeout=30)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(tmp)

def resource_estimate_warnings(cpus, memory_bytes, free_bytes):
    warnings = []
    if cpus < 4 or memory_bytes < 12 * 1024**3:
        warnings.append("Docker VM is below the 4 CPU / 12 GiB planning estimate")
    if free_bytes < 25 * 1024**3:
        warnings.append("repository filesystem free space is below the 25 GiB planning estimate")
    return warnings

def parse_k3d_version(output):
    match = re.search(r"(?m)^k3d version (v[0-9]+\.[0-9]+\.[0-9]+)\b", output)
    if not match: raise LabError("could not read k3d version from `k3d version`")
    return match.group(1)

def parse_kubectl_version(output):
    try:
        version = json.loads(output).get("clientVersion", {}).get("gitVersion")
    except (json.JSONDecodeError, AttributeError):
        version = None
    if not isinstance(version, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise LabError("could not read kubectl client version from JSON")
    return version

def parse_docker_version(output):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", output.strip())
    if not match: raise LabError("could not read Docker Engine server version")
    return tuple(int(part) for part in match.groups())

def check_cli_versions():
    k3d_output = run(["k3d", "version"], capture=True, timeout=10).stdout
    k3d_version = parse_k3d_version(k3d_output)
    kubectl_output = run(["kubectl", "version", "--client", "-o", "json"], capture=True, timeout=10).stdout
    kubectl_version = parse_kubectl_version(kubectl_output)
    python_version = sys.version_info[:3]
    mismatches = []
    if k3d_version != PINNED_K3D_VERSION:
        mismatches.append(f"k3d {k3d_version} (expected {PINNED_K3D_VERSION})")
    if kubectl_version != PINNED_KUBECTL_VERSION:
        mismatches.append(f"kubectl {kubectl_version} (expected {PINNED_KUBECTL_VERSION})")
    if python_version != PINNED_PYTHON_VERSION:
        actual_python = ".".join(str(part) for part in python_version)
        expected_python = ".".join(str(part) for part in PINNED_PYTHON_VERSION)
        mismatches.append(f"Python {actual_python} (expected {expected_python})")
    if mismatches:
        raise LabError("tool version mismatch: " + "; ".join(mismatches))
    say(f"Pinned tools: k3d {k3d_version}, kubectl {kubectl_version}, Python {'.'.join(map(str, python_version))}")

def listed_clusters():
    result = k3d_run("cluster", "list", "-o", "json", capture=True, check=False)
    if result.returncode:
        raise LabError("cannot inspect k3d clusters")
    try:
        clusters = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise LabError("k3d cluster list returned invalid JSON") from e
    if not isinstance(clusters, list) or any(not isinstance(cluster, dict) for cluster in clusters):
        raise LabError("k3d cluster list returned an unexpected JSON structure")
    return clusters

def preflight():
    missing = [x for x in ("docker", "k3d", "kubectl", "make") if not shutil.which(x)]
    if missing: raise LabError("missing tools: " + ", ".join(missing))
    check_cli_versions()
    p = run(["docker", "info", "--format", "{{.ServerVersion}} {{.NCPU}} {{.MemTotal}}"], capture=True, timeout=15)
    try:
        server, cpu_text, mem_text = p.stdout.strip().split()
        cpus, memory = int(cpu_text), int(mem_text)
    except (ValueError, TypeError): raise LabError("could not read Docker VM version/CPU/memory")
    docker_version = parse_docker_version(server)
    if docker_version < MIN_DOCKER_VERSION:
        minimum = ".".join(str(part) for part in MIN_DOCKER_VERSION)
        raise LabError(f"Docker Engine {server} is too old for pinned k3d; require {minimum} or newer")
    say(f"Docker daemon {server}; VM={cpus} CPUs, {memory // 1024**3} GiB RAM")
    for port in (8080, 8443, 3000, 5601):
        with socket.socket() as s:
            try: s.bind((HOST, port))
            except OSError: raise LabError(f"required loopback port {port} is already in use")
    free = shutil.disk_usage(ROOT).free
    estimates_not_met = resource_estimate_warnings(cpus, memory, free)
    say(f"Loopback ports available; repository filesystem free space {free // 1024**3} GiB.")
    say("Docker image-store free capacity is not measured by this host filesystem check.")
    if estimates_not_met:
        say("WARNING: " + "; ".join(estimates_not_met) + ". Estimates are unmeasured hypotheses, not support gates; continue only if you accept the possibility of setup failure.")
    else:
        say("Planning resource estimates met; these estimates are unmeasured and do not establish host support.")

def start_cluster():
    ensure_lab_dir(create=True)
    clusters = listed_clusters()
    if any(c.get("name") == CLUSTER for c in clusters):
        raise UnsafeTarget("a cluster with the lab name already exists; it will not be adopted automatically")
    owner_token = secrets.token_hex(16)
    atomic_json(OWNER_FILE, {"token": owner_token})
    atomic_json(STATE_FILE, {"cluster_owned_intent": True, "cluster_created": False, "state": "cluster_creating", "started_at": utc(), "lab": None})
    k3d_run("cluster", "create", "--config", ROOT / "cluster/k3d.yaml",
            "--k3s-node-label", f"lab.k3s-devops.invalid/owner={owner_token}@server:0",
            "--k3s-node-label", f"lab.k3s-devops.invalid/owner={owner_token}@agent:0,1",
            "--wait", "--timeout", "180s", timeout=240)
    finish_cluster_setup()

def finish_cluster_setup():
    ensure_lab_file(KUBECONFIG)
    k3d_run("kubeconfig", "write", CLUSTER, "--output", KUBECONFIG, timeout=30)
    os.chmod(KUBECONFIG, 0o600)
    try:
        owner = json.loads(OWNER_FILE.read_text())
        owner_token = owner["token"] if isinstance(owner, dict) else None
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e: raise UnsafeTarget("cannot prove ownership of the named cluster") from e
    if not isinstance(owner_token, str) or len(owner_token) != 32:
        raise UnsafeTarget("private lab ownership marker is malformed")
    agents = json.loads(kctl("get", "nodes", "-o", "json", capture=True).stdout).get("items", [])
    validate_cluster_nodes(agents)
    prefix = f"k3d-{CLUSTER}-agent-"
    agent_names = [n["metadata"]["name"] for n in agents if n["metadata"]["name"].startswith(prefix)
                   and n.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/owner") == owner_token]
    if len(agent_names) != 2: raise LabError("created cluster does not contain the configured two k3d agents")
    server_name = f"k3d-{CLUSTER}-server-0"
    server = next((n for n in agents if n.get("metadata", {}).get("name") == server_name), None)
    if not server or server.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/owner") != owner_token:
        raise UnsafeTarget("named cluster does not carry this creation's private owner marker")
    for name in agent_names:
        kctl("label", "node", name, "lab.k3s-devops.invalid/worker=true", "--overwrite")
    atomic_json(STATE_FILE, {"cluster_owned_intent": True, "cluster_created": True, "state": "provisioning", "started_at": utc(), "lab": None})

def recover_cluster_creation():
    clusters = listed_clusters()
    if any(c.get("name") == CLUSTER for c in clusters):
        finish_cluster_setup()
    else:
        start_cluster()

def wait_pods(namespace, selector, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        p = kctl("-n", namespace, "get", "pods", "-l", selector, "-o", "json", capture=True, check=False)
        if p.returncode == 0:
            try:
                items = json.loads(p.stdout).get("items", [])
                if items and all(any(c.get("type") == "Ready" and c.get("status") == "True" for c in i.get("status", {}).get("conditions", [])) for i in items): return
            except json.JSONDecodeError: pass
        time.sleep(2)
    raise LabError(f"timed out waiting for ready pods: {namespace}/{selector}")

def baseline():
    apply_file("deploy/namespace.yaml")
    validate_baseline()
    credentials = read_credentials()
    apply_secret("postgres-auth", "lab", {"POSTGRES_PASSWORD": credentials["postgres"], "APP_PASSWORD": credentials["app"]})
    apply_secret("orders-api-db", "lab", {"DB_PASSWORD": credentials["app"]})
    apply_secret("grafana-auth", "observability", {"password": credentials["grafana"]})
    apply_file("deploy/postgres.yaml")
    wait_pods("lab", "app=postgres")
    kctl("-n", "lab", "delete", "job", "db-bootstrap", "--ignore-not-found=true",
         "--wait=true", "--timeout=30s", timeout=40)
    apply_file("deploy/db-bootstrap.yaml")
    kctl("-n", "lab", "wait", "--for=condition=complete", "job/db-bootstrap", "--timeout=90s", timeout=100)
    for f in ("deploy/api.yaml", "deploy/ingress.yaml"):
        apply_file(f)
    run(["docker", "build", "-t", "k3s-devops-lab/orders-api:dev", "app"], timeout=300)
    k3d_run("image", "import", "k3s-devops-lab/orders-api:dev", "-c", CLUSTER, timeout=180)
    wait_rollout("orders-api")
    apply_file("app/traffic-deployment.yaml")
    kctl("-n", "observability", "delete", "job", "kibana-bootstrap", "--ignore-not-found=true",
         "--wait=true", "--timeout=30s", timeout=40)
    kctl("apply", "-k", ROOT / "observability", timeout=120)
    for name in ("prometheus", "grafana", "elasticsearch", "kibana", "kube-state-metrics"):
        wait_rollout(name, "observability", "300s")
    kctl("-n", "observability", "rollout", "status", "daemonset/fluent-bit", "--timeout=180s", timeout=190)
    kctl("-n", "observability", "wait", "--for=condition=complete", "job/kibana-bootstrap", "--timeout=300s", timeout=310)
    ensure_identity()

def read_credentials():
    path = LAB_DIR / "credentials.json"
    ensure_lab_file(path)
    missing = False
    try:
        credentials = json.loads(path.read_text())
    except FileNotFoundError:
        state = read_state()
        if state.get("cluster_created") or state.get("cluster_owned_intent"):
            raise LabError("private credentials are missing for an existing lab; restore credentials.json or run confirmed teardown before recreating the lab")
        missing = True
    except json.JSONDecodeError as e:
        raise LabError("private credentials file is invalid; refusing to replace it") from e
    if missing:
        credentials = {"postgres": secrets.token_urlsafe(32), "app": secrets.token_urlsafe(32), "grafana": secrets.token_urlsafe(32)}
        atomic_json(path, credentials)
    if not isinstance(credentials, dict) or any(not isinstance(credentials.get(key), str) or not credentials[key] for key in ("postgres", "app", "grafana")):
        raise LabError("private credentials file is incomplete or invalid")
    return credentials

def http_probe(path="/livez", host="orders.lab.test", timeout=5):
    req = urllib.request.Request("http://127.0.0.1:8080" + path, headers={"Host": host, "X-Request-ID": secrets.token_hex(16)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.headers.get("X-Request-ID"), r.read(4096)
    except urllib.error.HTTPError as e: return e.code, e.headers.get("X-Request-ID"), e.read(4096)

def direct_service_probe(path="/livez", timeout=5):
    try:
        with forwarded("orders-api", 80, "lab") as base:
            request = urllib.request.Request(base + path, headers={"Host": "orders.lab.test"})
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.status
            except urllib.error.HTTPError as e:
                return e.code
    except (LabError, OSError, urllib.error.URLError):
        return None

def service_selector_fault_observed(selector, ready_pods, ready_endpoints):
    return selector == {"app.kubernetes.io/name": "deliberately-absent"} and ready_pods >= 2 and ready_endpoints == 0

def api_service_selector_baseline(selector):
    return selector == {"app.kubernetes.io/name": "orders-api"}

def ingress_host_fault_observed(configured_hosts, ingress_status, service_status):
    return "wrong.lab.test" in configured_hosts and ingress_status == 404 and service_status == 200

def ingress_baseline_restored(spec):
    expected = {
        "rules": [{
            "host": "orders.lab.test",
            "http": {"paths": [{
                "path": "/",
                "pathType": "Prefix",
                "backend": {"service": {"name": "orders-api", "port": {"number": 80}}},
            }]},
        }],
    }
    return spec == expected

def latency_fault_observed(delay_setting, status, elapsed):
    return delay_setting == "0.8" and status == 200 and elapsed >= .7

def memory_fault_observed(startup_allocation, memory_limit, pods):
    return startup_allocation == "512" and memory_limit == "128Mi" and any(
        container.get("lastState", {}).get("terminated", {}).get("reason") == "OOMKilled"
        for pod in pods for container in pod.get("status", {}).get("containerStatuses", [])
    )

def memory_baseline_restored(startup_allocation, memory_limit):
    return startup_allocation is None and memory_limit == "256Mi"

def latency_baseline_restored(delay_setting):
    return delay_setting is None

def api_worker_selector_baseline(selector):
    return selector == {"lab.k3s-devops.invalid/worker": "true"}

def logging_fault_configured(config):
    return "Name stdout" in config and "Name es" not in config

def logging_baseline_configured(config):
    return "Name es" in config and "Name stdout" not in config

def metrics_fault_configured(annotations):
    return (annotations.get("prometheus.io/scrape") == "true"
            and annotations.get("prometheus.io/path") == "/missing-metrics"
            and annotations.get("prometheus.io/port") == "8000")

def metrics_baseline_configured(annotations):
    return (annotations.get("prometheus.io/scrape") == "true"
            and annotations.get("prometheus.io/path") == "/metrics"
            and annotations.get("prometheus.io/port") == "8000")

def postgres_pods_ready(pods):
    return len(pods) == 1 and any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pods[0].get("status", {}).get("conditions", [])
    )

def readiness_fault_observed(probe_path, pods, baseline_ready, orders_status):
    if probe_path != "/wrong-ready-path" or not baseline_ready or orders_status != 200:
        return False
    return any(
        pod.get("status", {}).get("phase") != "Pending"
        and any(condition.get("type") == "Ready" and condition.get("status") == "False"
                for condition in pod.get("status", {}).get("conditions", []))
        for pod in pods
    )

def scheduling_fault_observed(node_selector, pods, baseline_ready, orders_status):
    if node_selector != {"lab.k3s-devops.invalid/worker": "nowhere"} or not baseline_ready or orders_status != 200:
        return False
    return any(pod.get("status", {}).get("phase") == "Pending" for pod in pods)

def seeded_fixtures_present():
    status, _, body = http_probe("/orders")
    if status != 200: return False
    try: skus = {item.get("sku") for item in json.loads(body).get("items", [])}
    except (ValueError, TypeError, AttributeError): return False
    return {"FIXTURE-ALPHA", "FIXTURE-BRAVO", "FIXTURE-CHARLIE"} <= skus

@contextlib.contextmanager
def forwarded(service, remote_port, namespace="observability"):
    with socket.socket() as s:
        s.bind((HOST, 0)); local_port = s.getsockname()[1]
    proc = subprocess.Popen(["kubectl", "--kubeconfig", str(KUBECONFIG), "--context", CONTEXT,
                             "-n", namespace, "port-forward", "--address", HOST, f"svc/{service}", f"{local_port}:{remote_port}"],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if proc.poll() is not None: raise LabError(f"port-forward to {service} exited")
            try:
                with socket.create_connection((HOST, local_port), timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise LabError(f"port-forward to {service} did not become ready")
        yield f"http://{HOST}:{local_port}"
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=3)

def elastic_request_documents(request_id):
    with forwarded("elasticsearch", 9200) as base:
        url = base + "/orders-logs-*/_search?q=" + quote("http.request.id:" + request_id, safe="")
        with urllib.request.urlopen(url, timeout=4) as r: data = json.load(r)
    return [hit.get("_source", {}) for hit in data.get("hits", {}).get("hits", [])]

def elastic_has_request(request_id):
    try: return bool(elastic_request_documents(request_id))
    except (LabError, OSError, ValueError, urllib.error.URLError): return False

def elastic_search_ready():
    try:
        with forwarded("elasticsearch", 9200) as base:
            with urllib.request.urlopen(base + "/_cluster/health", timeout=5) as response:
                data = json.load(response)
        return data.get("status") in ("green", "yellow")
    except (LabError, OSError, ValueError, urllib.error.URLError):
        return False

def indexed_request_error(request_id, error_type, *, status_code=503, version=None):
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        return False
    try:
        documents = elastic_request_documents(request_id)
    except (LabError, OSError, ValueError, urllib.error.URLError):
        return False
    return any(
        document.get("http.request.id") == request_id
        and document.get("error.type") == error_type
        and document.get("http.response.status_code") == status_code
        and (version is None or document.get("service.version") == version)
        for document in documents
    )

def indexed_version_failure(request_id, version):
    return indexed_request_error(request_id, "synthetic_failure", version=version)

def prometheus_target_state():
    with forwarded("prometheus", 9090) as base:
        with urllib.request.urlopen(base + "/api/v1/targets?state=active", timeout=5) as r: data = json.load(r)
    targets = data.get("data", {}).get("activeTargets", [])
    return [t for t in targets if t.get("labels", {}).get("namespace") == "lab" and t.get("labels", {}).get("service") == "orders-api"]

def prometheus_alert_rules_ready():
    expected = {"OrdersApiHigh5xx", "OrdersApiHighP95", "OrdersApiMetricsMissing", "OrdersApiTargetMissing"}
    try:
        with forwarded("prometheus", 9090) as base:
            with urllib.request.urlopen(base + "/api/v1/rules?type=alert", timeout=8) as response: data = json.load(response)
        rules = {rule.get("name") for group in data.get("data", {}).get("groups", []) for rule in group.get("rules", [])}
        return data.get("status") == "success" and expected <= rules
    except (LabError, OSError, ValueError, urllib.error.URLError):
        return False

def kibana_dashboard_ready():
    expected_charts = {"request-volume-trend", "error-volume-trend", "ingestion-volume-trend"}
    expected_searches = {"api-incident-overview", "failed-orders", "database-timeouts", "ingestion-health"}
    try:
        with forwarded("kibana", 5601) as base:
            request = urllib.request.Request(base + "/api/saved_objects/dashboard/orders-incident-dashboard", headers={"kbn-xsrf": "true"})
            with urllib.request.urlopen(request, timeout=8) as response: data = json.load(response)
            if not isinstance(data, dict):
                return False
            charts = {ref.get("id") for ref in data.get("references", []) if isinstance(ref, dict) and ref.get("type") == "lens"}
            if data.get("type") != "dashboard" or data.get("id") != "orders-incident-dashboard" or not expected_charts <= charts:
                return False
            for object_id in expected_searches:
                request = urllib.request.Request(base + f"/api/saved_objects/search/{object_id}", headers={"kbn-xsrf": "true"})
                with urllib.request.urlopen(request, timeout=8) as response: saved_object = json.load(response)
                if not isinstance(saved_object, dict) or saved_object.get("type") != "search" or saved_object.get("id") != object_id:
                    return False
        return True
    except (LabError, OSError, ValueError, urllib.error.URLError):
        return False

def grafana_dashboards_ready():
    expected = {"orders-api-overview", "kubernetes-health"}
    try:
        credentials = json.loads((LAB_DIR / "credentials.json").read_text())
        password = credentials["grafana"]
        auth = base64.b64encode(f"labadmin:{password}".encode()).decode()
        with forwarded("grafana", 3000) as base:
            for uid in expected:
                request = urllib.request.Request(base + f"/apis/dashboard.grafana.app/v1/namespaces/default/dashboards/{uid}", headers={"Authorization": f"Basic {auth}"})
                with urllib.request.urlopen(request, timeout=8) as response: data = json.load(response)
                metadata = data.get("metadata", {})
                dashboard = data.get("spec", {})
                if metadata.get("name") != uid or not dashboard.get("panels"): return False
        return True
    except (OSError, KeyError, TypeError, ValueError, urllib.error.URLError, LabError):
        return False

def prometheus_query(query):
    with forwarded("prometheus", 9090) as base:
        url = base + "/api/v1/query?" + urlencode({"query": query})
        with urllib.request.urlopen(url, timeout=5) as r: data = json.load(r)
    results = data.get("data", {}).get("result", [])
    return [float(item["value"][1]) for item in results if len(item.get("value", [])) == 2]

def request_burst(count=16):
    return [status for status, _ in request_burst_results(count)]

def request_burst_results(count=16):
    def one(_):
        status, request_id, _ = http_probe("/orders")
        return status, request_id
    with ThreadPoolExecutor(max_workers=min(count, 16)) as pool:
        return list(pool.map(one, range(count)))

def deployment_object():
    return json.loads(kctl("-n", "lab", "get", "deployment", "orders-api", "-o", "json", capture=True).stdout)

def api_baseline_ready():
    deployment = deployment_object()
    if deployment.get("spec", {}).get("replicas") != 2:
        return False
    service = json.loads(kctl("-n", "lab", "get", "service", "orders-api", "-o", "json", capture=True).stdout)
    if not api_service_selector_baseline(service.get("spec", {}).get("selector", {})):
        return False
    status = deployment.get("status", {})
    if status.get("readyReplicas", 0) < 2 or status.get("availableReplicas", 0) < 2:
        return False
    pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
    ready_pods = sum(
        any(condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", []))
        for pod in pods
    )
    if ready_pods < 2:
        return False
    slices = json.loads(kctl("-n", "lab", "get", "endpointslices", "-l", "kubernetes.io/service-name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
    ready_endpoints = sum(
        bool(endpoint.get("addresses")) and endpoint.get("conditions", {}).get("ready") is True
        for endpoint_slice in slices
        for endpoint in endpoint_slice.get("endpoints", [])
    )
    return ready_endpoints >= 2

def api_restart_snapshot():
    pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
    ready = [pod for pod in pods if any(c.get("type") == "Ready" and c.get("status") == "True" for c in pod.get("status", {}).get("conditions", []))]
    if len(ready) != 2: return None
    return tuple(sorted((pod["metadata"]["name"], sum(c.get("restartCount", 0) for c in pod.get("status", {}).get("containerStatuses", []))) for pod in ready))

def deployment_env(key):
    containers = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    env = next((c.get("env", []) for c in containers if c.get("name") == "api"), [])
    item = next((x for x in env if x.get("name") == key), None)
    return item.get("value") if item else None

def deployment_probe_path(kind):
    containers = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    c = next((x for x in containers if x.get("name") == "api"), {})
    return c.get(f"{kind}Probe", {}).get("httpGet", {}).get("path")

def worker_candidate():
    p = kctl("get", "nodes", "-o", "json", capture=True)
    nodes = json.loads(p.stdout).get("items", [])
    prefix = f"k3d-{CLUSTER}-agent-"
    agents = [n for n in nodes if n["metadata"]["name"].startswith(prefix) and n.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/worker") == "true" and not n.get("spec", {}).get("unschedulable") and any(c.get("type") == "Ready" and c.get("status") == "True" for c in n.get("status", {}).get("conditions", []))]
    if len(agents) != 2: raise LabError("need exactly two Ready, schedulable lab agents for worker exercise")
    deployment = deployment_object()
    deployment_spec = deployment.get("spec", {})
    if deployment_spec.get("replicas") != 2 or not api_worker_selector_baseline(deployment_spec.get("template", {}).get("spec", {}).get("nodeSelector", {})):
        raise LabError("API deployment is not at its two-replica worker baseline; refusing drain")
    pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
    ready_pods = [pod for pod in pods if any(c.get("type") == "Ready" and c.get("status") == "True" for c in pod.get("status", {}).get("conditions", []))]
    placed = {pod.get("spec", {}).get("nodeName") for pod in ready_pods}
    agent_names = {node["metadata"]["name"] for node in agents}
    if len(ready_pods) != 2 or placed != agent_names:
        raise LabError("exactly two Ready API replicas must be spread across both lab workers; refusing drain")
    return next((n["metadata"]["name"] for n in agents if n["metadata"]["name"] in placed), None)

def worker_fault_observed(node, deployment, pods):
    if node.get("spec", {}).get("unschedulable") is not True:
        return False
    if deployment.get("spec", {}).get("replicas") != 2 or deployment.get("status", {}).get("readyReplicas", 0) != 1:
        return False
    return any(
        pod.get("status", {}).get("phase") == "Pending"
        for pod in pods
        if pod.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/name") == "orders-api"
    )

def uncordon_recorded_worker(worker):
    prefix = f"k3d-{CLUSTER}-agent-"
    if not isinstance(worker, str) or not worker.startswith(prefix):
        raise UnsafeTarget("recorded worker name is outside the dedicated lab cluster")
    p = kctl("get", "node", worker, "-o", "json", capture=True, check=False)
    if p.returncode:
        raise LabError("recorded lab worker is missing; refusing a different node")
    node = json.loads(p.stdout)
    if node.get("metadata", {}).get("labels", {}).get("lab.k3s-devops.invalid/worker") != "true":
        raise UnsafeTarget("recorded node is not labeled as a dedicated lab worker")
    kctl("uncordon", worker, timeout=30)

def suite_repair(lab):
    if lab not in SCENARIOS: raise LabError("LAB must be a value from 01 through 12")
    ensure_identity()
    state = read_state()
    if state.get("state") != "active" or state.get("lab") != lab:
        raise LabError("suite repair requires the matching active incident")
    if lab == "10":
        kctl("apply", "--dry-run=server", "-k", ROOT / "observability", timeout=120)
        kctl("apply", "-k", ROOT / "observability", timeout=120)
    elif lab == "12":
        validate_file("deploy/api.yaml")
        uncordon_recorded_worker(state.get("worker_node"))
        apply_file("deploy/api.yaml")
    elif lab == "04":
        apply_file("deploy/ingress.yaml")
    else:
        apply_file("deploy/api.yaml")

def suite_check_log(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", request_id):
        raise LabError("suite log check requires a generated UUID request ID")
    ensure_identity()
    state = read_state()
    if state.get("state") != "healthy" or state.get("lab"):
        raise LabError("suite log retention check requires a healthy lab with no active incident")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if elastic_has_request(request_id):
            say("Suite history request remains indexed after repeated up and scenario resets.")
            return
        time.sleep(3)
    raise LabError("suite history request was not found in Elasticsearch after scenario resets")

def suite_api_request(method, path, body=None, request_id=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Host": "orders.lab.test"}
    if request_id: headers["X-Request-ID"] = request_id
    if data is not None: headers["Content-Type"] = "application/json"
    with forwarded("orders-api", 80, "lab") as base:
        request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.load(response)

def suite_order_create(sku, request_id):
    if not isinstance(sku, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", sku):
        raise LabError("suite order SKU contains unsupported characters")
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", request_id):
        raise LabError("suite order creation requires a generated UUID request ID")
    ensure_identity()
    status, _ = suite_api_request("POST", "/orders", {"sku": sku, "quantity": 1}, request_id)
    if status != 201: raise LabError(f"suite order creation returned HTTP {status}")
    say("Synthetic suite order created through the dedicated lab Service.")

def suite_order_check(sku):
    if not isinstance(sku, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", sku):
        raise LabError("suite order check requires a valid synthetic SKU")
    ensure_identity()
    state = read_state()
    if state.get("state") != "healthy" or state.get("lab"):
        raise LabError("suite order retention check requires a healthy lab with no active incident")
    status, data = suite_api_request("GET", "/orders?" + urlencode({"sku": sku}))
    if status != 200 or not any(item.get("sku") == sku for item in data.get("items", [])):
        raise LabError(f"suite persistence check did not find recent order {sku}")
    say("Synthetic suite order remains in the database.")

def up():
    s = read_state()
    if s.get("state") == "deleting":
        raise LabError("teardown is in progress; finish make down CONFIRM=yes before starting the lab")
    if s.get("lab"): raise LabError("incident active; run make lab-reset")
    preflight()
    read_credentials()
    if s.get("cluster_created"):
        if not KUBECONFIG.exists(): raise LabError("cluster lifecycle record exists but its dedicated kubeconfig is missing; refusing implicit adoption")
        ensure_identity(allow_bootstrap=s.get("state") in ("provisioning", "provisioning_failed"))
    elif s.get("cluster_owned_intent"):
        recover_cluster_creation()
    else:
        start_cluster()
    atomic_json(STATE_FILE, {"cluster_created": True, "state": "provisioning", "started_at": utc(), "lab": None})
    try:
        baseline()
    except Exception as e:
        atomic_json(STATE_FILE, {"cluster_created": True, "state": "provisioning_failed", "failed_at": utc(), "error": str(e), "lab": None})
        raise
    atomic_json(STATE_FILE, {"cluster_created": True, "state": "healthy", "healthy_at": utc(), "lab": None})
    say("Healthy lab baseline is ready.")

def detect(lab):
    # Return true only when the scenario's intended symptom is observable.
    if lab == "01":
        service = json.loads(kctl("-n", "lab", "get", "service", "orders-api", "-o", "json", capture=True).stdout)
        p = kctl("-n", "lab", "get", "endpointslice", "-l", "kubernetes.io/service-name=orders-api", "-o", "json", capture=True)
        pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
        ready_pods = [pod for pod in pods if any(c.get("type") == "Ready" and c.get("status") == "True" for c in pod.get("status", {}).get("conditions", []))]
        ready_endpoints = sum(bool(ep.get("addresses")) and ep.get("conditions", {}).get("ready") is True for x in json.loads(p.stdout).get("items", []) for ep in x.get("endpoints", []))
        return service_selector_fault_observed(service.get("spec", {}).get("selector", {}), len(ready_pods), ready_endpoints)
    if lab in ("02", "09"):
        pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
        baseline_ready = api_baseline_ready()
        orders_status = http_probe("/orders")[0]
        if lab == "02":
            return readiness_fault_observed(deployment_probe_path("readiness"), pods, baseline_ready, orders_status)
        selector = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("nodeSelector", {})
        return scheduling_fault_observed(selector, pods, baseline_ready, orders_status)
    if lab == "03":
        if deployment_env("DB_HOST") != "postgres-missing.lab.svc.cluster.local": return False
        postgres_pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app=postgres", "-o", "json", capture=True).stdout).get("items", [])
        if not postgres_pods_ready(postgres_pods): return False
        if http_probe("/livez")[0] != 200: return False
        status, request_id, _ = http_probe("/orders")
        if status != 503 or not request_id: return False
        state = read_state()
        atomic_json(STATE_FILE, {**state, "evidence_request_id": request_id})
        return indexed_request_error(request_id, "db_dns_error")
    if lab == "04":
        ingress = json.loads(kctl("-n", "lab", "get", "ingress", "orders-api", "-o", "json", capture=True).stdout)
        hosts = [rule.get("host") for rule in ingress.get("spec", {}).get("rules", [])]
        ingress_status = http_probe("/livez")[0]
        return ingress_host_fault_observed(hosts, ingress_status, direct_service_probe("/livez"))
    if lab == "05":
        if deployment_env("APP_VERSION") != "v2" or deployment_env("FAULT_FAIL_PERCENT") != "35": return False
        state = read_state()
        request_id = state.get("evidence_request_id")
        if request_id and indexed_version_failure(request_id, "v2"):
            return True
        for _ in range(8):
            status, request_id, _ = http_probe("/orders")
            if status >= 500 and request_id:
                atomic_json(STATE_FILE, {**state, "evidence_request_id": request_id})
                return indexed_version_failure(request_id, "v2")
        return False
    if lab == "06":
        start = time.monotonic(); status, _, _ = http_probe("/orders")
        return latency_fault_observed(deployment_env("FAULT_DELAY_GET"), status, time.monotonic() - start)
    if lab == "07":
        if deployment_env("DB_POOL_MAX") != "1" or deployment_env("DB_HOLD_SECONDS") != "1.5": return False
        state = read_state()
        request_id = state.get("evidence_request_id")
        if request_id and indexed_request_error(request_id, "db_pool_timeout"):
            return True
        for status, candidate in request_burst_results(16):
            if status >= 500 and candidate:
                atomic_json(STATE_FILE, {**state, "evidence_request_id": candidate})
                if indexed_request_error(candidate, "db_pool_timeout"):
                    return True
        return False
    if lab == "08":
        p = kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True)
        containers = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        api = next((container for container in containers if container.get("name") == "api"), {})
        return memory_fault_observed(deployment_env("FAULT_STARTUP_ALLOC_MB"), api.get("resources", {}).get("limits", {}).get("memory"), json.loads(p.stdout).get("items", []))
    if lab == "10":
        if not elastic_search_ready(): return False
        config = json.loads(kctl("-n", "observability", "get", "configmap", "fluent-bit-config", "-o", "json", capture=True).stdout).get("data", {}).get("fluent-bit.conf", "")
        if not logging_fault_configured(config): return False
        status, request_id, _ = http_probe("/orders")
        if status != 200 or not request_id: return False
        atomic_json(STATE_FILE, {**read_state(), "evidence_request_id": request_id})
        pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
        stdout_seen = False
        for pod in pods:
            logs = kctl("-n", "lab", "logs", pod["metadata"]["name"], "--since=2m", capture=True, check=False)
            stdout_seen = stdout_seen or request_id in (logs.stdout or "")
        return stdout_seen and not elastic_has_request(request_id)
    if lab == "11":
        service = json.loads(kctl("-n", "lab", "get", "service", "orders-api", "-o", "json", capture=True).stdout)
        annotations = service.get("metadata", {}).get("annotations", {})
        if not metrics_fault_configured(annotations): return False
        if http_probe("/orders")[0] != 200: return False
        targets = prometheus_target_state()
        if not targets or not all(t.get("health") == "down" for t in targets): return False
        status, request_id, _ = http_probe("/orders")
        if status != 200 or not request_id: return False
        return elastic_has_request(request_id)
    if lab == "12":
        worker = read_state().get("worker_node")
        if not worker: return False
        node = json.loads(kctl("get", "node", worker, "-o", "json", capture=True).stdout)
        deployment = deployment_object()
        pods = json.loads(kctl("-n", "lab", "get", "pods", "-l", "app.kubernetes.io/name=orders-api", "-o", "json", capture=True).stdout).get("items", [])
        return worker_fault_observed(node, deployment, pods) and http_probe("/livez")[0] == 200 and http_probe("/orders")[0] == 200
    return False

def lab_start(lab):
    if lab not in SCENARIOS: raise LabError("LAB must be a value from 01 through 12")
    ensure_identity()
    s = read_state()
    if s.get("state") != "healthy" or s.get("lab"): raise LabError("baseline must be healthy and no incident may be active")
    value = {"cluster_created": True, "state": "starting", "lab": lab, "title": SCENARIOS[lab][0], "run_id": secrets.token_hex(8), "started_at": utc()}
    if lab == "06":
        with contextlib.suppress(LabError, OSError, ValueError):
            samples = prometheus_query('histogram_quantile(0.95, sum by (le) (rate(orders_http_request_duration_seconds_bucket{route="/orders"}[1m])))')
            value["p95_baseline_seconds"] = samples[0] if samples else None
    atomic_json(STATE_FILE, value)
    try:
        if lab == "12":
            if not api_baseline_ready(): raise LabError("API baseline is not healthy; refusing worker drain")
            if http_probe("/livez")[0] != 200 or http_probe("/orders")[0] != 200:
                raise LabError("API liveness and database-backed Orders checks must pass before worker drain")
            worker = worker_candidate()
            if not worker: raise LabError("no worker with a ready API replica found")
            value["worker_node"] = worker
            atomic_json(STATE_FILE, value)
            kctl("cordon", worker, timeout=30)
            kctl("drain", worker, "--ignore-daemonsets", "--delete-emptydir-data", "--timeout=120s", timeout=130)
        else:
            apply_file(SCENARIOS[lab][1])
            if lab == "10": kctl("-n", "observability", "rollout", "status", "daemonset/fluent-bit", "--timeout=90s", timeout=100)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if detect(lab):
                value = read_state()
                value.update(state="active", symptom_observed_at=utc()); atomic_json(STATE_FILE, value)
                say(f"Lab {lab} active: {SCENARIOS[lab][0]}"); return
            time.sleep(2)
        raise LabError("scenario symptom not observed before deadline")
    except Exception as e:
        value.update(state="start_failed", error=str(e), failed_at=utc()); atomic_json(STATE_FILE, value)
        raise

def verify_recovery(lab):
    if lab == "01":
        return api_baseline_ready() and detect("01") is False and all(http_probe("/livez")[0] == 200 for _ in range(5)) and all(http_probe("/orders")[0] == 200 for _ in range(3))
    if lab == "02":
        if deployment_probe_path("readiness") != "/readyz": return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        return rolled_out and api_baseline_ready() and detect("01") is False and http_probe("/livez")[0] == 200 and http_probe("/orders")[0] == 200
    if lab == "09":
        selector = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("nodeSelector", {})
        if not api_worker_selector_baseline(selector): return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        return rolled_out and api_baseline_ready() and detect("01") is False and http_probe("/livez")[0] == 200 and http_probe("/orders")[0] == 200
    if lab == "03":
        if deployment_env("DB_HOST") != "postgres.lab.svc.cluster.local": return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        if not rolled_out or not api_baseline_ready(): return False
        status, request_id, _ = http_probe("/orders")
        if status != 200 or not request_id: return False
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                docs = elastic_request_documents(request_id)
                if docs: return all(doc.get("error.type") != "db_dns_error" for doc in docs)
            except (LabError, OSError, ValueError, urllib.error.URLError): pass
            time.sleep(3)
        return False
    if lab == "04":
        ingress = json.loads(kctl("-n", "lab", "get", "ingress", "orders-api", "-o", "json", capture=True).stdout)
        if not ingress_baseline_restored(ingress.get("spec", {})):
            return False
        return all(http_probe("/livez")[0] == 200 for _ in range(5)) and direct_service_probe("/livez") == 200
    if lab == "05":
        if deployment_env("APP_VERSION") != "v1": return False
        if deployment_env("FAULT_FAIL_PERCENT") is not None: return False
        labels = deployment_object().get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
        if labels.get("app.kubernetes.io/version") != "v1": return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        if not rolled_out: return False
        request_id = read_state().get("evidence_request_id")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if indexed_version_failure(request_id, "v2"):
                return all(http_probe("/orders")[0] == 200 for _ in range(8))
            time.sleep(3)
        return False
    if lab == "06":
        if not latency_baseline_restored(deployment_env("FAULT_DELAY_GET")): return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        if not rolled_out or not api_baseline_ready(): return False
        for _ in range(3):
            start = time.monotonic(); status, _, _ = http_probe("/orders")
            if status != 200 or time.monotonic() - start >= .7: return False
        saved = read_state().get("p95_baseline_seconds")
        limit = max(float(saved) * 1.5, float(saved) + .1) if saved is not None else .5
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            samples = prometheus_query('histogram_quantile(0.95, sum by (le) (rate(orders_http_request_duration_seconds_bucket{route="/orders"}[1m])))')
            if samples and samples[0] <= limit: return True
            time.sleep(5)
        return False
    if lab == "08":
        containers = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        api = next((container for container in containers if container.get("name") == "api"), {})
        if not memory_baseline_restored(deployment_env("FAULT_STARTUP_ALLOC_MB"), api.get("resources", {}).get("limits", {}).get("memory")):
            return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=90s"], timeout=100, check=False).returncode == 0
        if detect("08") or not rolled_out or http_probe("/livez")[0] != 200 or http_probe("/orders")[0] != 200: return False
        restart_snapshot = api_restart_snapshot()
        if restart_snapshot is None: return False
        observation_end = time.monotonic() + 15
        while time.monotonic() < observation_end:
            time.sleep(min(5, observation_end - time.monotonic()))
            if detect("08") or api_restart_snapshot() != restart_snapshot: return False
        return True
    if lab == "07":
        if deployment_env("DB_POOL_MAX") != "5" or deployment_env("DB_HOLD_SECONDS") is not None: return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        if not rolled_out or not api_baseline_ready(): return False
        request_id = read_state().get("evidence_request_id")
        if not indexed_request_error(request_id, "db_pool_timeout"):
            return False
        return all(status < 500 for status, _ in request_burst_results(4))
    if lab == "10":
        config = kctl("-n", "observability", "get", "configmap", "fluent-bit-config", "-o", "json", capture=True)
        if not logging_baseline_configured(json.loads(config.stdout).get("data", {}).get("fluent-bit.conf", "")): return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "observability", "rollout", "status", "daemonset/fluent-bit", "--timeout=90s"], timeout=100, check=False).returncode == 0
        if not rolled_out: return False
        status, request_id, _ = http_probe("/orders")
        if status != 200: return False
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if elastic_has_request(request_id): return True
            time.sleep(3)
        return False
    if lab == "11":
        service = json.loads(kctl("-n", "lab", "get", "service", "orders-api", "-o", "json", capture=True).stdout)
        annotations = service.get("metadata", {}).get("annotations", {})
        if not metrics_baseline_configured(annotations): return False
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            targets = prometheus_target_state()
            if targets and all(t.get("health") == "up" for t in targets):
                metric = 'orders_http_requests_total{route="/orders"}'
                before = prometheus_query(f"max(timestamp({metric}))")
                baseline_timestamp = max(before) if before else None
                if http_probe("/orders")[0] != 200: return False
                sample_deadline = time.monotonic() + 45
                while time.monotonic() < sample_deadline:
                    samples = prometheus_query(f"max(timestamp({metric}))")
                    if samples and (baseline_timestamp is None or samples[0] > baseline_timestamp): return True
                    time.sleep(3)
                return False
            if read_state().get("state") == "active" and targets and all(t.get("health") == "down" for t in targets): return False
            time.sleep(5)
        return False
    if lab == "12":
        worker = read_state().get("worker_node")
        if not worker: return False
        node = json.loads(kctl("get", "node", worker, "-o", "json", capture=True).stdout)
        if node.get("spec", {}).get("unschedulable"):
            return False
        rolled_out = run(["kubectl", "--kubeconfig", KUBECONFIG, "--context", CONTEXT, "-n", "lab", "rollout", "status", "deployment/orders-api", "--timeout=60s"], timeout=70, check=False).returncode == 0
        if not rolled_out: return False
        selector = deployment_object().get("spec", {}).get("template", {}).get("spec", {}).get("nodeSelector", {})
        if not api_worker_selector_baseline(selector): return False
        if not api_baseline_ready():
            return False
        try:
            worker_candidate()
        except LabError:
            return False
        return http_probe("/livez")[0] == 200 and http_probe("/orders")[0] == 200
    return False

def lab_verify(lab):
    ensure_identity(); s = read_state()
    if not lab or lab != s.get("lab"): raise LabError("LAB must match the active incident")
    if s.get("state") != "active": raise LabError("the incident has not reached active state; inspect status and reset if needed")
    if verify_recovery(lab): say(f"Recovery verified for lab {lab}."); return
    raise LabError(f"recovery checks failed for lab {lab}; repair the fault, then retry make lab-verify LAB={lab}")

def lab_reset():
    ensure_identity(); s = read_state(); lab = s.get("lab")
    if not lab:
        say("No active incident."); return
    validate_baseline()
    s.update(state="resetting", reset_started_at=utc()); atomic_json(STATE_FILE, s)
    if s.get("worker_node"):
        uncordon_recorded_worker(s["worker_node"])
    # Apply only project baseline objects; never delete the namespace or PVC.
    for f in ("deploy/ingress.yaml", "deploy/api.yaml", "deploy/postgres.yaml"):
        apply_file(f)
    if lab == "12":
        kctl("-n", "lab", "rollout", "restart", "deployment/orders-api", timeout=30)
    kctl("apply", "-k", ROOT / "observability", timeout=120)
    kctl("-n", "observability", "rollout", "status", "daemonset/fluent-bit", "--timeout=180s", timeout=190)
    wait_rollout("orders-api", timeout="180s")
    recovery_window = utc()
    if not verify_recovery(lab): raise LabError("baseline recovery checks failed; incident state retained for retry")
    if not seeded_fixtures_present(): raise LabError("seeded database fixtures are missing; incident state retained for review")
    atomic_json(STATE_FILE, {"cluster_created": True, "state": "healthy", "lab": None, "last_reset": {"lab": lab, "at": utc(), "run_id": s.get("run_id"), "recovery_traffic_started_at": recovery_window, "recovery_traffic_completed_at": utc()}})
    say(f"Lab {lab} reset; database PVC and telemetry history retained.")

def doctor():
    ensure_identity(); checks = []
    status, rid, _ = http_probe("/livez"); checks.append(("ingress/livez", status == 200, f"HTTP {status}"))
    status, rid, _ = http_probe("/orders"); checks.append(("database-backed orders", status == 200, f"HTTP {status}"))
    p = kctl("-n", "lab", "exec", "deploy/orders-api", "--", "python", "-c", "import socket; socket.gethostbyname('postgres.lab.svc.cluster.local')", capture=True, check=False)
    checks.append(("service DNS", p.returncode == 0, (p.stdout or p.stderr or "probe failed").strip()[:200]))
    elastic_ok = False
    deadline = time.monotonic() + 45
    while rid and time.monotonic() < deadline:
        try:
            if elastic_has_request(rid): elastic_ok = True; break
        except LabError: pass
        time.sleep(3)
    checks.append(("indexed request ID", elastic_ok, rid or "request ID missing"))
    checks.append(("Kibana incident dashboard", kibana_dashboard_ready(), "dashboard and Lens chart references"))
    checks.append(("Grafana dashboards", grafana_dashboards_ready(), "API Overview and Kubernetes Health"))
    checks.append(("Prometheus alert rules", prometheus_alert_rules_ready(), "four expected rule names loaded"))
    metrics_ok = False
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if prometheus_query('orders_http_requests_total{route="/orders"}'):
                metrics_ok = True; break
        except (LabError, OSError, ValueError): pass
        time.sleep(3)
    checks.append(("recent Prometheus series", metrics_ok, "orders_http_requests_total route=/orders"))
    for name, ok, detail in checks: say(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    return all(x[1] for x in checks)

def urls():
    say("Orders API: http://orders.lab.test:8080 (add 127.0.0.1 orders.lab.test to hosts file)")
    say("Grafana: run `kubectl --kubeconfig .lab/kubeconfig --context k3d-k3s-devops-lab -n observability port-forward svc/grafana 3000:3000`")
    say("Kibana: run `kubectl --kubeconfig .lab/kubeconfig --context k3d-k3s-devops-lab -n observability port-forward svc/kibana 5601:5601`")

def diagnostics():
    ensure_identity()
    # Export a narrow allowlist; raw Kubernetes objects and event messages can
    # contain hostnames, addresses, labels, and other identifying metadata.
    objects = {"pods": [], "nodes": [], "events": []}
    p = kctl("-n", "lab", "get", "pods", "-o", "json", capture=True, check=False)
    if p.returncode == 0:
        for pod in json.loads(p.stdout).get("items", []):
            status = pod.get("status", {})
            objects["pods"].append({
                "phase": status.get("phase"),
                "ready": any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])),
                "restarts": sum(c.get("restartCount", 0) for c in status.get("containerStatuses", [])),
                "reasons": [c.get("state", {}).get("waiting", {}).get("reason") or c.get("state", {}).get("terminated", {}).get("reason") for c in status.get("containerStatuses", [])],
            })
    p = kctl("get", "nodes", "-o", "json", capture=True, check=False)
    if p.returncode == 0:
        for node in json.loads(p.stdout).get("items", []):
            conditions = node.get("status", {}).get("conditions", [])
            objects["nodes"].append({"ready": next((c.get("status") == "True" for c in conditions if c.get("type") == "Ready"), False),
                                     "unschedulable": bool(node.get("spec", {}).get("unschedulable"))})
    p = kctl("-n", "lab", "get", "events", "-o", "json", capture=True, check=False)
    if p.returncode == 0:
        for event in json.loads(p.stdout).get("items", []):
            objects["events"].append({"type": event.get("type"), "reason": event.get("reason"), "count": event.get("count", 1)})
    # Names, messages, object metadata, credentials, and addresses are omitted.
    out = LAB_DIR / f"diagnostics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    state = read_state()
    safe_state = public_state_view(state, ("state", "lab", "title", "started_at", "healthy_at", "last_reset"))
    atomic_json(out, {"collected_at": utc(), "cluster": CLUSTER, "state": safe_state, "objects": objects})
    say(f"Sanitized diagnostics written to {out.relative_to(ROOT)}; review before sharing.")

def down(confirmed=False):
    if not confirmed: raise UnsafeTarget("teardown requires explicit confirmation: make down CONFIRM=yes")
    with mutation_lock():
        s = read_state()
        deleting = s.get("state") == "deleting"
        if not s.get("cluster_created") and not deleting and not s.get("cluster_owned_intent"):
            raise LabError("no recorded lab-owned cluster; refusing deletion")
        if s.get("cluster_owned_intent") and not s.get("cluster_created") and not deleting:
            present = any(c.get("name") == CLUSTER for c in listed_clusters())
            if not present:
                cleanup_lab_files()
                atomic_json(STATE_FILE, {"cluster_created": False, "state": "absent", "deleted_at": utc()})
                say("Interrupted lab creation left no cluster; private creation state was cleaned up.")
                return
            # Finish writing the private kubeconfig and validating the recorded
            # node owner token before any deletion is considered.
            try:
                recover_cluster_creation()
            except LabError:
                # A partially registered cluster cannot satisfy the normal
                # three-node identity check. Delete it only if every visible
                # node and the private kubeconfig still prove this creation.
                ensure_partial_creation_identity()
                k3d_run("cluster", "delete", CLUSTER, timeout=180)
                cleanup_lab_files()
                atomic_json(STATE_FILE, {"cluster_created": False, "state": "absent", "deleted_at": utc()})
                say("Owner-verified partial lab cluster deleted after interrupted creation.")
                return
            s = read_state()
        if deleting:
            present = any(c.get("name") == CLUSTER for c in listed_clusters())
            if not present:
                cleanup_lab_files()
                atomic_json(STATE_FILE, {"cluster_created": False, "state": "absent", "deleted_at": utc()})
                say("Dedicated cluster was already absent; local teardown cleanup completed.")
                return
        if not KUBECONFIG.exists(): raise LabError("dedicated lab kubeconfig is missing; refusing cluster deletion")
        ensure_identity(allow_bootstrap=s.get("state") in ("provisioning", "provisioning_failed"), allow_version_mismatch=True)
        if s.get("lab"): raise LabError("active incident; reset before down")
        if not deleting:
            s.update(state="deleting", delete_started_at=utc()); atomic_json(STATE_FILE, s)
        k3d_run("cluster", "delete", CLUSTER, timeout=180)
        # Remove only files beneath the repository's dedicated .lab directory.
        cleanup_lab_files()
        atomic_json(STATE_FILE, {"cluster_created": False, "state": "absent", "deleted_at": utc()})
        say("Dedicated lab cluster deleted. The caller kubeconfig was not used or modified.")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("preflight", "up", "doctor", "urls", "lab-list", "lab-status", "lab-start", "lab-verify", "lab-reset", "suite-repair", "suite-check-log", "suite-order-create", "suite-order-check", "diagnostics", "down"))
    p.add_argument("lab", nargs="?")
    p.add_argument("request_id", nargs="?")
    p.add_argument("--yes", action="store_true", help="confirm deletion of the dedicated lab cluster and its PVC data")
    a = p.parse_args()
    try:
        if a.command == "preflight": preflight()
        elif a.command == "lab-list":
            for key, (title, _) in SCENARIOS.items(): say(public_scenario_label(key, title))
        elif a.command == "lab-status": say(json.dumps(public_state_view(read_state()), indent=2))
        elif a.command == "urls": urls()
        elif a.command == "up":
            with mutation_lock(): up()
        elif a.command == "down": down(a.yes)
        elif a.command == "doctor":
            if not doctor(): raise LabError("one or more doctor checks failed")
        elif a.command == "lab-start":
            with mutation_lock(): lab_start(a.lab)
        elif a.command == "lab-verify": lab_verify(a.lab)
        elif a.command == "lab-reset":
            with mutation_lock(): lab_reset()
        elif a.command == "suite-repair":
            with mutation_lock(): suite_repair(a.lab)
        elif a.command == "suite-check-log": suite_check_log(a.lab)
        elif a.command == "suite-order-create": suite_order_create(a.lab, a.request_id)
        elif a.command == "suite-order-check": suite_order_check(a.lab)
        elif a.command == "diagnostics": diagnostics()
    except (LabError, OSError, ValueError, KeyError) as e:
        fail(str(e), 2 if isinstance(e, UnsafeTarget) else 1)

if __name__ == "__main__": main()
