#!/usr/bin/env python3
"""Ajoute un hote a inventories/home/hosts.yml en preservant les
commentaires existants (ruamel.yaml, edition round-trip). Cree le groupe
cible s'il n'existe pas encore. Echoue si l'hote existe deja, dans
n'importe quel groupe, pour eviter les doublons silencieux.

Prerequis sur le control-node : apt install python3-ruamel.yaml

Usage :
    scripts/add-host.py --group webservers --name web02 --ip 192.168.10.55
"""
import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

INVENTORY_PATH = Path(__file__).resolve().parent.parent / "inventories" / "home" / "hosts.yml"


def find_existing_host(children, name):
    for group_name, group in (children or {}).items():
        hosts = (group or {}).get("hosts") or {}
        if name in hosts:
            return group_name
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, help="Groupe d'inventaire cible (cree s'il n'existe pas)")
    parser.add_argument("--name", required=True, help="Nom de la VM (doit correspondre au vm_name Terraform)")
    parser.add_argument("--ip", required=True, help="Adresse IP (ansible_host)")
    args = parser.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=2, offset=0)

    with open(INVENTORY_PATH, encoding="utf-8") as f:
        data = yaml.load(f)

    children = data["all"]["children"]

    existing_group = find_existing_host(children, args.name)
    if existing_group is not None:
        print(f"Erreur : l'hote '{args.name}' existe deja dans le groupe '{existing_group}'.", file=sys.stderr)
        sys.exit(1)

    if children.get(args.group) is None:
        children[args.group] = {"hosts": {}}
    if children[args.group].get("hosts") is None:
        children[args.group]["hosts"] = {}

    children[args.group]["hosts"][args.name] = {"ansible_host": args.ip}

    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    print(f"Hote '{args.name}' ({args.ip}) ajoute au groupe '{args.group}'.")


if __name__ == "__main__":
    main()
