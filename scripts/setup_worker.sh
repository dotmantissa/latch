#!/usr/bin/env bash
# Run as root only on the dedicated Latch worker, through its private SSH channel.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [[ $EUID -ne 0 ]] || [[ $(hostname -s) != latch-worker ]]; then
  printf '%s\n' 'This setup requires root on the dedicated latch-worker host.' >&2
  exit 1
fi
. /etc/os-release
if [[ $ID != ubuntu ]] || [[ $VERSION_ID != 24.04 && $VERSION_ID != 26.04 ]]; then
  printf '%s\n' 'A supported Ubuntu LTS worker is required.' >&2
  exit 1
fi

install -d -m 0755 /etc/apt/keyrings /opt/latch
install -d -m 0700 /var/lib/latch /var/lib/latch/provenance
apt-get update
apt-get install -y ca-certificates curl gnupg python3 python3-venv nftables
curl --fail --silent --show-error --proto '=https' \
  https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $VERSION_CODENAME
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
curl --fail --silent --show-error --proto '=https' \
  https://gvisor.dev/archive.key -o /etc/apt/keyrings/gvisor.asc
gpg --batch --yes --dearmor -o /etc/apt/keyrings/gvisor.gpg /etc/apt/keyrings/gvisor.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/gvisor.gpg] https://storage.googleapis.com/gvisor/releases release main\n' \
  "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/gvisor.list
apt-get update

# Resolve signed repository candidates once, install exactly those versions, retain the manifest.
LATCH_PACKAGES=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin runsc)
LATCH_INSTALL=()
for LATCH_PACKAGE in "${LATCH_PACKAGES[@]}"; do
  LATCH_VERSION=$(apt-cache policy "$LATCH_PACKAGE" | awk '/Candidate:/ {print $2}')
  if [[ -z $LATCH_VERSION || $LATCH_VERSION == '(none)' ]]; then
    printf 'No signed repository candidate for %s.\n' "$LATCH_PACKAGE" >&2
    exit 1
  fi
  LATCH_INSTALL+=("$LATCH_PACKAGE=$LATCH_VERSION")
done
printf '%s\n' "${LATCH_INSTALL[@]}" > /var/lib/latch/provenance/apt-versions.txt
apt-get install -y "${LATCH_INSTALL[@]}"
runsc install
systemctl enable docker
systemctl restart docker

# The operator uses sudo; the application and browser never receive Docker access.
cat > /etc/ssh/sshd_config.d/00-latch-worker.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers linuxuser
X11Forwarding no
AllowTcpForwarding no
EOF
sshd -t
systemctl reload ssh

python3 - <<'PY'
import datetime
import json
import pathlib
import subprocess

def output(args):
    return subprocess.check_output(args, text=True).strip()

info = json.loads(output(['docker', 'info', '--format', '{{json .}}']))
if 'runsc' not in info.get('Runtimes', {}):
    raise SystemExit('gVisor runtime registration failed')
report = {
    'at': datetime.datetime.now(datetime.UTC).isoformat(),
    'scope': 'worker_host_installation',
    'os_release': pathlib.Path('/etc/os-release').read_text(),
    'kernel': output(['uname', '-r']),
    'docker': output(['docker', '--version']),
    'gvisor': output(['runsc', '--version']),
    'cgroup_version': info.get('CgroupVersion'),
    'runtimes': sorted(info['Runtimes']),
    'packages': pathlib.Path('/var/lib/latch/provenance/apt-versions.txt').read_text().splitlines(),
    'containment': 'not_yet_validated',
}
path = pathlib.Path('/var/lib/latch/provenance/host.json')
path.write_text(json.dumps(report, indent=2) + '\n')
path.chmod(0o600)
print(json.dumps(report, indent=2))
PY
