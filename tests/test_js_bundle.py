from mobiflow.config import StackConfig
from mobiflow.llm import extract_fenced_files
from mobiflow.maestro import parse_flow_bundle


def test_stack_js_enabled():
    assert StackConfig(language="yaml+js").js_enabled()
    assert StackConfig(language="javascript").js_enabled()
    assert not StackConfig(language="yaml").js_enabled()


def test_extract_fenced_yaml_and_js():
    text = """
Here you go:

```yaml flow.yaml
appId: com.android.settings
---
- runScript: scripts/helpers.js
- launchApp
- stopApp
```

```javascript scripts/helpers.js
output.ok = true;
```
"""
    files = extract_fenced_files(text)
    names = {n for n, _ in files}
    assert "flow.yaml" in names
    assert "scripts/helpers.js" in names


def test_parse_flow_bundle():
    text = """
```yaml
appId: org.wikipedia
---
- runScript: helpers.js
- launchApp
```

```js helpers.js
output.ready = true;
```
"""
    bundle = parse_flow_bundle(text, app_id="org.wikipedia")
    assert "appId: org.wikipedia" in bundle.flow_yaml
    assert "stopApp" in bundle.flow_yaml
    assert bundle.has_js
    assert any(p.endswith("helpers.js") for p in bundle.scripts)
    assert "runScript: scripts/" in bundle.flow_yaml or "helpers.js" in bundle.flow_yaml
