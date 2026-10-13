import subprocess
from pathlib import Path


def test_interface_translation_model():
    subprocess.run(["node", "--test", str(Path(__file__).with_name("i18n.test.cjs"))], check=True)
