# INFRA-ANSIBLE-PVE-HOME

Configuration logicielle des VM provisionnees par
[INFRA-TERRAFORM-PVE-HOME](https://github.com/Xenus775/INFRA-TERRAFORM-PVE-HOME)
sur mon Proxmox personnel.

Ce depot est responsable **uniquement** de la configuration logicielle
(paquets, services, durcissement). La creation des VM (CPU, RAM, disque,
reseau, Cloud-Init) est geree par le depot Terraform.

## Prerequis

- [Ansible](https://docs.ansible.com/) (paquet `ansible`, pas seulement
  `ansible-core` : les roles utilisent la collection `community.general`)
- Un acces SSH par cle au compte `ansible` sur chaque VM cible

Installation sur une machine Debian/Ubuntu :

```bash
sudo apt update && sudo apt install -y git ansible
```

## Architecture

Ansible s'execute depuis une VM dediee, `LPRANSIBLE01` (control-node,
192.168.10.120, creee par le depot Terraform). Voir `DECISIONS.txt` pour le
raisonnement complet (Ansible ne tourne pas nativement sous Windows sans
WSL).

```
Terraform (depot separe)
    |
    v
VM prete (Cloud-Init applique, SSH disponible)
    |
    v
git clone INFRA-ANSIBLE-PVE-HOME (sur LPRANSIBLE01)
    |
    v
ansible-playbook site.yml
    |
    v
VM configuree (paquets, SSH durci, agent QEMU, fuseau horaire)
```

## Inventaire

Inventaire statique dans `inventories/home/hosts.yml`. Exemple actuel :

```yaml
all:
  vars:
    ansible_user: ansible
  children:
    control_node:
      hosts:
        LPRANSIBLE01:
          ansible_host: 192.168.10.120
```

Le script `scripts/generate-inventory.ps1` du depot Terraform peut regenerer
ce fichier automatiquement a partir des outputs Terraform apres un `terraform
apply`.

## Variables

Variables communes dans `inventories/home/group_vars/all.yml` (ex:
`common_timezone`). Variables par role dans `roles/<role>/defaults/main.yml`.

## Roles

| Role | Contenu |
|---|---|
| `common` | Mises a jour de securite, paquets de base, agent QEMU actif, fuseau horaire, synchronisation horaire |
| `ssh` | Durcissement SSH : pas de connexion root, pas d'authentification par mot de passe |
| `apache` | Installation et activation du serveur web Apache (`apache2`) |
| `postgresql` | Installation de PostgreSQL, mot de passe du role `postgres` genere aleatoirement |
| `mysql` | Installation de MariaDB, securisation de base (suppression comptes anonymes/base test), mot de passe root genere aleatoirement |
| `wordpress` | Stack LAMP + WordPress installe et configure via WP-CLI (base + compte admin generes) |
| `exploitation_account` | Cree un compte local `exploitation` (groupe `sudo`, mot de passe genere aleatoirement) sur une VM |

Les roles `apache`, `postgresql`, `mysql` et `wordpress` ne sont pas
appliques par `site.yml` : chacun cible son propre groupe d'inventaire via
un playbook dedie, sur le meme modele :

| Playbook | Groupe cible | Role |
|---|---|---|
| `webserver.yml` | `webservers` (actuellement : `web01`) | `apache` |
| `postgres.yml` | `postgres_servers` | `postgresql` |
| `mysql.yml` | `mysql_servers` | `mysql` |
| `wordpress.yml` | `wordpress_servers` | `wordpress` |

Les roles `postgresql`, `mysql` et `wordpress` suivent la meme logique
d'idempotence que `exploitation_account` : un fichier sentinelle
(`/root/.ansible_provisioned_<service>`) evite de regenerer les mots de
passe lors d'un re-run. Les identifiants generes sont affiches une seule
fois via des lignes marqueurs machine-lisibles (`POSTGRES_PASSWORD`,
`MYSQL_ROOT_PASSWORD`, `WORDPRESS_DB`, `WORDPRESS_ADMIN` — meme convention
que `EXPLOITATION_PASSWORD`), jamais stockes ailleurs.

Le role `exploitation_account` n'est pas non plus applique par `site.yml` :
il est declenche via le playbook `exploitation-account.yml`, cible avec
`--limit <nom-vm>` a chaque nouvelle VM cree par Terraform (voir le script
`scripts/provision-vm.ps1` du depot Terraform, qui automatise l'ensemble :
mise a jour de l'inventaire, push, puis execution de ce playbook depuis
LPRANSIBLE01).

Ce compte est concu comme un compte de secours (break-glass), avec un
acces SSH qui depend du type de VM :
- **VM d'administration** (groupe `control_node`, ex: LPRANSIBLE01) : le
  mot de passe n'est utilisable que localement (console Proxmox) ou via
  `su` — le role `ssh` desactive `PasswordAuthentication` globalement,
  sans exception pour ce compte.
- **Toute autre VM** (ex: `web01`) : le role ajoute un bloc `Match User
  exploitation` dans `sshd_config` qui autorise la connexion SSH par mot
  de passe pour ce compte precis (`PubkeyAuthentication no` pour ce
  compte, puisqu'aucune cle ne lui est jamais associee). Le compte
  `ansible` utilise par Ansible garde son acces par cle intact : le bloc
  `Match` ne s'applique qu'a l'utilisateur `exploitation`.

Le mot de passe n'est genere qu'une seule fois : si le compte existe deja,
le role ne le regenere pas (evite une rotation accidentelle lors d'un
re-run).

## Connexion SSH

`ansible.cfg` utilise par defaut :

```ini
remote_user = ansible
private_key_file = ~/.ssh/id_ed25519_pve_admin
```

Cette cle est dediee au projet (voir `DECISIONS.txt`) : sa cle publique est
injectee via Cloud-Init dans toutes les VM provisionnees par Terraform, et sa
cle privee vit sur le control-node `LPRANSIBLE01` (`~/.ssh/`).

`host_key_checking = False` est active dans `ansible.cfg` : reseau personnel
de confiance, prompts d'acceptation de cle desactives par choix assume pour
la simplicite (voir `DECISIONS.txt`).

## Secrets

**Aucun secret n'est commite dans ce depot.** Aucun secret n'est aujourd'hui
necessaire (authentification uniquement par cle SSH). Si un secret devient
necessaire (mot de passe applicatif, token), il devra passer par Ansible
Vault — voir `DECISIONS.txt`. Le `.gitignore` anticipe deja les fichiers de
mot de passe de vault.

## Lancer les playbooks

Depuis le control-node (`LPRANSIBLE01`) :

```bash
git clone git@github.com:Xenus775/INFRA-ANSIBLE-PVE-HOME.git
cd INFRA-ANSIBLE-PVE-HOME
ansible-galaxy collection install -r requirements.yml

ansible-playbook --syntax-check site.yml
ansible-playbook site.yml
```

Pour cibler une seule VM :

```bash
ansible-playbook site.yml --limit LPRANSIBLE01
```

Pour verifier ce qui changerait sans l'appliquer :

```bash
ansible-playbook site.yml --check --diff
```

## Ajouter une nouvelle VM

1. Provisionnez-la avec Terraform (voir INFRA-TERRAFORM-PVE-HOME).
2. Ajoutez-la dans `inventories/home/hosts.yml`, dans le groupe approprie
   (creez un nouveau groupe si besoin, par exemple pour un futur groupe de
   VM de service).
3. `ansible-playbook site.yml --limit <nom-de-la-vm>` pour l'appliquer sans
   toucher aux autres hotes.

## Ajouter un role

```bash
mkdir -p roles/mon_role/{tasks,defaults,handlers}
```

Ajoutez-le a `site.yml` (globalement) ou a un nouveau playbook cible si le
role ne concerne qu'un sous-ensemble de VM.

## Tests

```bash
ansible-playbook --syntax-check site.yml
ansible-lint            # si installe
ansible all -m ping     # verifie la connectivite SSH sur tout l'inventaire
```

## Troubleshooting

- **`UNREACHABLE` / timeout SSH** : verifiez que la VM est demarree et que
  `ansible_host` dans l'inventaire correspond a son IP reelle (voir les
  outputs du depot Terraform).
- **`sudo: a password is required`** : le compte `ansible` cree par
  Cloud-Init doit disposer d'un sudo sans mot de passe (verifie a la creation
  de `LPRANSIBLE01`).
- **Module `community.general.timezone` introuvable** : lancez
  `ansible-galaxy collection install -r requirements.yml`.

## Bonnes pratiques / workflow recommande

1. `git pull` avant toute modification.
2. `ansible-playbook --syntax-check site.yml` avant tout run reel.
3. `ansible-playbook site.yml --check --diff` pour previsualiser les
   changements avant de les appliquer pour de vrai.
4. Ne jamais desactiver une protection SSH existante sans raison documentee
   dans `DECISIONS.txt`.
