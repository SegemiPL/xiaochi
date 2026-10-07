"""Product identity and user-facing conventions shared by Web and CLI."""
from pathlib import Path

import yaml

PRODUCT = yaml.safe_load(Path(__file__).with_name('xiaochi.yaml').read_text(encoding='utf-8'))
AGENT_NAME = PRODUCT['name']
DISCLAIMER = PRODUCT['disclaimer']
