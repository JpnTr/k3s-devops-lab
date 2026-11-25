#!/usr/bin/env python3
"""Parse local YAML/JSON assets and check internal Markdown links."""
import json, re, sys
from pathlib import Path
from urllib.parse import unquote
import yaml
from markdown_links import heading_anchors

ROOT = Path(__file__).resolve().parents[1]
errors = []

# Keep the declared direct Python dependencies immutable. Transitive versions are currently
# unresolved by a checked-in lock file and are documented as a release gap.
requirement_pattern = re.compile(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9.!+_-]*")
for relative in ("app/requirements.txt", "requirements-dev.txt"):
    requirement_file = ROOT / relative
    dependency_count = 0
    seen_names = set()
    try:
        for line_number, raw in enumerate(requirement_file.read_text().splitlines(), 1):
            requirement = raw.strip()
            if not requirement or requirement.startswith("#"):
                continue
            if not requirement_pattern.fullmatch(requirement):
                errors.append(f"{relative}:{line_number}: direct dependencies must use exact == pins")
            else:
                name = re.sub(r"[-_.]+", "-", requirement.split("==", 1)[0].split("[", 1)[0]).lower()
                if name in seen_names:
                    errors.append(f"{relative}:{line_number}: duplicate normalized dependency {name}")
                seen_names.add(name)
                dependency_count += 1
    except OSError as e:
        errors.append(f"{relative}: cannot read dependency pins: {e}")
    if dependency_count == 0:
        errors.append(f"{relative}: at least one direct pinned dependency is required")

for pattern in ("**/*.yaml", "**/*.yml"):
    for path in ROOT.glob(pattern):
        if ".git" in path.parts or ".lab" in path.parts: continue
        try:
            list(yaml.safe_load_all(path.read_text()))
        except Exception as e: errors.append(f"{path.relative_to(ROOT)}: YAML: {e}")

# Check the local inputs consumed by Kustomize before the controller asks the
# dedicated cluster API to render and validate them with server-side dry-run.
for path in ROOT.rglob("kustomization.yaml"):
    if ".git" in path.parts or ".lab" in path.parts: continue
    try:
        config = yaml.safe_load(path.read_text()) or {}
        if not isinstance(config, dict):
            errors.append(f"{path.relative_to(ROOT)}: Kustomize document must be a mapping")
            continue
        for resource in config.get("resources", []):
            target = path.parent / resource
            if not target.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing Kustomize resource {resource}")
        for generator_name in ("configMapGenerator", "secretGenerator"):
            for generator in config.get(generator_name, []):
                for entry in generator.get("files", []):
                    source = entry.split("=", 1)[-1]
                    if not (path.parent / source).is_file():
                        errors.append(f"{path.relative_to(ROOT)}: missing {generator_name} file {source}")
    except (OSError, AttributeError, TypeError, yaml.YAMLError) as e:
        errors.append(f"{path.relative_to(ROOT)}: invalid Kustomize inputs: {e}")

for path in ROOT.rglob("*.json"):
    if ".git" in path.parts or ".lab" in path.parts: continue
    try: json.loads(path.read_text())
    except Exception as e: errors.append(f"{path.relative_to(ROOT)}: JSON: {e}")

for path in ROOT.rglob("*.ndjson"):
    if ".git" in path.parts or ".lab" in path.parts: continue
    records = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        try:
            record = json.loads(line)
            records.append((i, record))
        except Exception as e: errors.append(f"{path.relative_to(ROOT)}:{i}: NDJSON: {e}")
    record_keys = [(record.get("type"), record.get("id")) for _, record in records]
    keys = set(record_keys)
    if len(record_keys) != len(keys):
        errors.append(f"{path.relative_to(ROOT)}: duplicate saved-object type/id pair")
    if path.name == "kibana-objects.ndjson":
        expected_lens = {"request-volume-trend", "error-volume-trend", "ingestion-volume-trend"}
        actual_lens = {record.get("id") for _, record in records if record.get("type") == "lens"}
        if not expected_lens <= actual_lens:
            errors.append(f"{path.relative_to(ROOT)}: missing expected Kibana Lens charts: {sorted(expected_lens - actual_lens)}")
    for i, record in records:
        for ref in record.get("references", []):
            if (ref.get("type"), ref.get("id")) not in keys:
                errors.append(f"{path.relative_to(ROOT)}:{i}: unresolved saved-object reference {ref.get('type')}/{ref.get('id')}")
        if path.name == "kibana-objects.ndjson" and record.get("type") == "lens":
            attrs = record.get("attributes", {})
            state = attrs.get("state", {}) if isinstance(attrs, dict) else {}
            data_sources = state.get("datasourceStates", {}) if isinstance(state, dict) else {}
            form_based = data_sources.get("formBased", {}) if isinstance(data_sources, dict) else {}
            layers = form_based.get("layers", {}) if isinstance(form_based, dict) else {}
            visualization = state.get("visualization", {}) if isinstance(state, dict) else {}
            visual_layers = {layer.get("layerId"): layer for layer in visualization.get("layers", []) if isinstance(layer, dict)} if isinstance(visualization, dict) else {}
            if not isinstance(attrs, dict) or attrs.get("visualizationType") != "lnsXY" or not isinstance(layers, dict) or not layers:
                errors.append(f"{path.relative_to(ROOT)}:{i}: Lens chart must define an XY visualization and form-based data layer")
            if isinstance(layers, dict):
                for layer_id, layer in layers.items():
                    if not isinstance(layer, dict):
                        errors.append(f"{path.relative_to(ROOT)}:{i}: Lens data layer must be an object")
                        continue
                    columns = layer.get("columns", {})
                    visual = visual_layers.get(layer_id, {})
                    accessors = visual.get("accessors", []) if isinstance(visual, dict) else []
                    required = [visual.get("xAccessor"), *accessors] if isinstance(accessors, list) and isinstance(visual, dict) else []
                    if not isinstance(columns, dict) or not required or any(column not in columns for column in required):
                        errors.append(f"{path.relative_to(ROOT)}:{i}: Lens chart references a missing data column")
                    if not any(ref.get("type") == "index-pattern" and ref.get("name") == f"indexpattern-datasource-layer-{layer_id}" for ref in record.get("references", [])):
                        errors.append(f"{path.relative_to(ROOT)}:{i}: Lens chart lacks its index-pattern layer reference")
        if path.name == "kibana-objects.ndjson" and record.get("type") == "dashboard" and record.get("id") == "orders-incident-dashboard":
            chart_ids = {ref.get("id") for ref in record.get("references", []) if ref.get("type") == "lens"}
            if not expected_lens <= chart_ids:
                errors.append(f"{path.relative_to(ROOT)}:{i}: incident dashboard does not reference all expected Lens charts")
        panels_json = record.get("attributes", {}).get("panelsJSON")
        if panels_json:
            try:
                panels = json.loads(panels_json)
                refs = record.get("references", [])
                ref_names = {ref.get("name") for ref in refs}
                for panel in panels:
                    if not isinstance(panel, dict):
                        errors.append(f"{path.relative_to(ROOT)}:{i}: dashboard panel must be an object")
                        continue
                    panel_ref = panel.get("panelRefName")
                    if panel_ref not in ref_names:
                        errors.append(f"{path.relative_to(ROOT)}:{i}: dashboard panel has no matching saved-object reference")
                    elif not any(ref.get("name") == panel_ref and ref.get("type") == panel.get("type") for ref in refs):
                        errors.append(f"{path.relative_to(ROOT)}:{i}: dashboard panel type does not match its saved-object reference")
            except (TypeError, json.JSONDecodeError) as e:
                errors.append(f"{path.relative_to(ROOT)}:{i}: invalid dashboard panelsJSON: {e}")

# Ensure the public scenario catalog points to real exercise assets.
catalog_path = ROOT / "scenarios/catalog.yaml"
try:
    catalog = yaml.safe_load(catalog_path.read_text())
    entries = catalog["catalog"]
    expected = {f"{i:02d}" for i in range(1, 13)}
    ids = [str(item["id"]) for item in entries]
    if set(ids) != expected or len(ids) != len(expected): errors.append("scenarios/catalog.yaml: expected unique IDs 01 through 12")
    for item in entries:
        for field in ("fault", "student"):
            if not (ROOT / item[field]).is_file():
                errors.append(f"scenarios/catalog.yaml: {item['id']} missing {field} asset {item[field]}")
        student_file = ROOT / item["student"]
        if student_file.is_file():
            student_text = student_file.read_text()
            for hint in range(1, 4):
                if student_text.count(f"**Hint {hint} ·") != 1:
                    errors.append(f"scenarios/catalog.yaml: {item['id']} student brief must contain Hint {hint} exactly once")
        instructor_path, _, anchor = item["instructor"].partition("#")
        instructor_file = ROOT / instructor_path
        if not instructor_file.is_file():
            errors.append(f"scenarios/catalog.yaml: {item['id']} missing instructor file {instructor_path}")
        elif anchor:
            headings = heading_anchors(instructor_file.read_text())
            if anchor not in headings:
                errors.append(f"scenarios/catalog.yaml: {item['id']} missing instructor heading #{anchor}")
        for field in ("detector", "verifier", "reset"):
            source_path, separator, symbol = item[field].partition(":")
            source_file = ROOT / source_path
            if not separator or not source_file.is_file() or f"def {symbol}(" not in source_file.read_text():
                errors.append(f"scenarios/catalog.yaml: {item['id']} missing {field} implementation {item[field]}")
        suite_path = ROOT / item["automated_suite"]
        if not suite_path.is_file():
            errors.append(f"scenarios/catalog.yaml: {item['id']} missing automated suite {item['automated_suite']}")
except (OSError, KeyError, TypeError, yaml.YAMLError) as e:
    errors.append(f"scenarios/catalog.yaml: invalid catalog: {e}")

# Alert names are part of the observability contract checked by make doctor.
try:
    rules = yaml.safe_load((ROOT / "observability/rules.yml").read_text())
    expected_alerts = {"OrdersApiHigh5xx", "OrdersApiHighP95", "OrdersApiMetricsMissing", "OrdersApiTargetMissing"}
    alert_names = [str(rule.get("alert")) for group in rules.get("groups", []) for rule in group.get("rules", [])]
    actual_alerts = set(alert_names)
    if actual_alerts != expected_alerts or len(alert_names) != len(expected_alerts):
        errors.append(f"observability/rules.yml: expected alerts {sorted(expected_alerts)}, got {sorted(actual_alerts)}")
except (OSError, AttributeError, TypeError, yaml.YAMLError) as e:
    errors.append(f"observability/rules.yml: invalid alert rules: {e}")

# Keep the runtime doctor IDs aligned with the provisioned Grafana dashboard files.
for filename, expected_uid in (("orders-overview.json", "orders-api-overview"), ("kubernetes-health.json", "kubernetes-health")):
    try:
        dashboard = json.loads((ROOT / "observability" / filename).read_text())
        if dashboard.get("uid") != expected_uid or not dashboard.get("panels"):
            errors.append(f"observability/{filename}: expected UID {expected_uid} and at least one panel")
    except (OSError, AttributeError, TypeError, json.JSONDecodeError) as e:
        errors.append(f"observability/{filename}: invalid Grafana dashboard: {e}")

# Keep every external image reference aligned with the pin inventory.
try:
    version_manifest = yaml.safe_load((ROOT / "versions.yaml").read_text())
    if not isinstance(version_manifest, dict):
        raise TypeError("manifest root must be a mapping")
    pins = version_manifest.get("images")
    tool_versions = version_manifest.get("tools")
    if not isinstance(pins, dict):
        raise TypeError("images must be a mapping")
    if not isinstance(tool_versions, dict):
        raise TypeError("tools must be a mapping")
    pinned_images = set(pins.values())
    def find_images(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "image" and isinstance(child, str): yield child
                else: yield from find_images(child)
        elif isinstance(value, list):
            for child in value: yield from find_images(child)
    for pattern in ("**/*.yaml", "**/*.yml"):
        for path in ROOT.glob(pattern):
            if ".git" in path.parts or ".lab" in path.parts: continue
            for document in yaml.safe_load_all(path.read_text()):
                for image in find_images(document):
                    if image.startswith("k3s-devops-lab/"): continue
                    if image not in pinned_images:
                        errors.append(f"{path.relative_to(ROOT)}: image not pinned in versions.yaml: {image}")
    dockerfile = (ROOT / "app/Dockerfile").read_text().splitlines()
    base = next((line.split()[1] for line in dockerfile if line.startswith("FROM ")), None)
    if base != pins.get("api"): errors.append("app/Dockerfile: base image differs from versions.yaml api pin")
    api_python = re.match(r"python:(\d+\.\d+\.\d+)", pins.get("api", ""))
    if not api_python:
        errors.append("versions.yaml: API Python image must include a pinned three-part version")
    controller = (ROOT / "scripts/lab.py").read_text()
    for key, constant in (("k3d", "PINNED_K3D_VERSION"), ("kubectl", "PINNED_KUBECTL_VERSION")):
        value = tool_versions.get(key)
        declared = re.search(rf"(?m)^{constant} = \"([^\"]+)\"$", controller)
        if not value or not declared or declared.group(1) != value:
            errors.append(f"scripts/lab.py / versions.yaml: {constant} must match tools.{key}")
    k3s_image_tag = pins.get("k3s-node")
    k3s_tool_tag = tool_versions.get("k3s")
    image_version = k3s_image_tag.rsplit(":", 1)[1] if isinstance(k3s_image_tag, str) and ":" in k3s_image_tag else None
    k3s_node_version = re.sub(r"-k3s([0-9]+)$", r"+k3s\1", k3s_tool_tag if isinstance(k3s_tool_tag, str) else "")
    declared_k3s = re.search(r'(?m)^PINNED_K3S_NODE_VERSION = "([^"]+)"$', controller)
    if not k3s_tool_tag or k3s_tool_tag != image_version or not declared_k3s or declared_k3s.group(1) != k3s_node_version:
        errors.append("scripts/lab.py / versions.yaml: K3s node version must match tools.k3s and images.k3s-node")
    if not api_python:
        errors.append("versions.yaml: API Python image must include a pinned three-part version")
    else:
        declared_python = re.search(r"(?m)^PINNED_PYTHON_VERSION = \((\d+), (\d+), (\d+)\)$", controller)
        if not declared_python or ".".join(declared_python.groups()) != api_python.group(1):
            errors.append("scripts/lab.py / versions.yaml: Python preflight version must match API image pin")
except (OSError, KeyError, TypeError, yaml.YAMLError, IndexError) as e:
    errors.append(f"versions.yaml: invalid image pin inventory: {e}")

link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
for path in ROOT.rglob("*.md"):
    if ".git" in path.parts or ".lab" in path.parts: continue
    for target in link_pattern.findall(path.read_text()):
        target = target.split(None, 1)[0].strip("<>")
        if not target or "://" in target or target.startswith("mailto:"): continue
        local_target, separator, fragment = target.partition("#")
        local_target = unquote(local_target)
        local = (path.parent / local_target).resolve() if local_target else path.resolve()
        if not local.exists(): errors.append(f"{path.relative_to(ROOT)}: missing link target {target}")
        elif separator and fragment and local.suffix.lower() == ".md":
            anchors = heading_anchors(local.read_text())
            if unquote(fragment) not in anchors:
                errors.append(f"{path.relative_to(ROOT)}: missing heading anchor {target}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Static YAML/JSON/NDJSON, direct Python pins, tool version pins, Python version alignment, image pins, scenario references, and Markdown paths/anchors passed.")
