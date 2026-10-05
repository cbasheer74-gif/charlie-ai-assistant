import py_compile
import unittest
import sys

files = [
    "memory/config_manager.py",
    "core/groq_client.py",
    "engine/ai/providers.py",
    "engine/ai/registry.py",
    "engine/ai/core.py",
    "engine/hybrid_brain.py",
    "tests/test_groq_provider.py",
]

print("--- PY_COMPILE ---")
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK: {f}")
    except Exception as e:
        print(f"FAIL: {f} -> {e}")
        sys.exit(1)

print("\n--- UNITTESTS ---")
suite = unittest.defaultTestLoader.discover("tests", pattern="test_groq_provider.py")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
if not result.wasSuccessful():
    sys.exit(1)
print("ALL TESTS PASSED")
