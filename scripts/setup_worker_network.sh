#!/usr/bin/env bash
# Install only on the verified dedicated worker after reviewing the explicit egress policy.
set -euo pipefail
if [[ $EUID -ne 0 ]] || [[ $(hostname -s) != latch-worker ]]; then
  printf '%s\n' 'Root on the dedicated latch-worker is required.' >&2
  exit 1
fi
if ! id latch-egress >/dev/null 2>&1; then
  useradd --system --home /var/lib/latch/proxy --shell /usr/sbin/nologin latch-egress
fi
LATCH_PROXY_UID=$(id -u latch-egress)
install -d -m 0755 /opt/latch/services/common /opt/latch/services/supervisor
install -d -m 0750 -o root -g latch-egress /var/lib/latch/proxy-tls
if id latch-supervisor >/dev/null 2>&1; then
  chmod 0751 /var/lib/latch
else
  chmod 0750 /var/lib/latch
fi
chown root:latch-egress /var/lib/latch
chown root:latch-egress /var/lib/latch/egress-policy.json
chmod 0640 /var/lib/latch/egress-policy.json
printf '%s\n' 'nameserver 127.0.0.53' 'options timeout:2 attempts:2' \
  > /var/lib/latch/proxy-resolv.conf
chmod 0644 /var/lib/latch/proxy-resolv.conf

python3 - <<'PY'
import json
import pathlib
import subprocess
import sys
sys.path.insert(0, '/opt/latch')
from services.supervisor.egress import EgressPolicy
policy = EgressPolicy(json.loads(pathlib.Path('/var/lib/latch/egress-policy.json').read_text()))
network = subprocess.run(['docker', 'network', 'inspect', 'latch_egress'], capture_output=True)
if network.returncode:
    subprocess.run(['docker', 'network', 'create', '--internal', '--subnet', '172.29.240.0/24',
                    '--opt', 'com.docker.network.bridge.name=latch-br0', 'latch_egress'], check=True)
else:
    value = json.loads(network.stdout)[0]
    if (not value['Internal'] or value['IPAM']['Config'][0]['Subnet'] != '172.29.240.0/24'
            or value['Options'].get('com.docker.network.bridge.name') != 'latch-br0'):
        raise SystemExit('Existing network does not match the required boundary')
tls = pathlib.Path('/var/lib/latch/proxy-tls')
def run(args):
    subprocess.run(['openssl', *args], check=True, capture_output=True)
if not (tls/'ca.key').exists():
    run(['req', '-x509', '-newkey', 'rsa:3072', '-sha256', '-days', '365', '-nodes',
         '-subj', '/CN=Latch worker inspection CA', '-addext', 'basicConstraints=critical,CA:TRUE',
         '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
         '-keyout', str(tls/'ca.key'), '-out', str(tls/'ca.crt')])
    (tls/'ca.key').chmod(0o600)
for host in policy.hosts:
    if (tls/(host+'.crt')).exists():
        continue
    config=tls/(host+'.ext')
    config.write_text('subjectAltName=DNS:'+host+'\nbasicConstraints=critical,CA:FALSE\n'
                      'keyUsage=critical,digitalSignature,keyEncipherment\n'
                      'extendedKeyUsage=serverAuth\n')
    run(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN='+host,
         '-keyout', str(tls/(host+'.key')), '-out', str(tls/(host+'.csr'))])
    run(['x509', '-req', '-in', str(tls/(host+'.csr')), '-CA', str(tls/'ca.crt'),
         '-CAkey', str(tls/'ca.key'), '-set_serial', '0x'+__import__('secrets').token_hex(16),
         '-days', '30', '-sha256', '-extfile', str(config), '-out', str(tls/(host+'.crt'))])
    subprocess.run(['chown', 'root:latch-egress', str(tls/(host+'.key'))], check=True)
    (tls/(host+'.key')).chmod(0o640)
    (tls/(host+'.csr')).unlink()
    config.unlink()
for host in policy.hosts:
    # Send the public inspection CA in the chain so Chromium can verify its exact SPKI pin.
    (tls/(host+'.chain.crt')).write_bytes((tls/(host+'.crt')).read_bytes()
                                        + (tls/'ca.crt').read_bytes())
import base64, hashlib
public = subprocess.check_output(['openssl', 'x509', '-in', str(tls/'ca.crt'), '-pubkey', '-noout'])
der = subprocess.check_output(['openssl', 'pkey', '-pubin', '-outform', 'DER'], input=public)
spki = base64.b64encode(hashlib.sha256(der).digest()).decode()
pathlib.Path('/var/lib/latch/provenance/proxy-ca-spki.txt').write_text(spki+'\n')
print(json.dumps({'proxy_ca_spki':spki, 'approved_page_count':len(policy.pages),
                  'approved_hosts':sorted(policy.hosts), 'expires_at':policy.expires_at.isoformat()}))
PY

sed "s/@LATCH_PROXY_UID@/$LATCH_PROXY_UID/g" /opt/latch/infra/worker/network.nft \
  > /etc/latch-worker.nft
install -m 0644 /opt/latch/infra/worker/latch-network.service /etc/systemd/system/
install -m 0644 /opt/latch/infra/worker/latch-egress.service /etc/systemd/system/
nft add table inet latch_worker
nft --check -f /etc/latch-worker.nft
nft -f /etc/latch-worker.nft
if command -v ufw >/dev/null && [[ $(ufw status) == 'Status: active'* ]]; then
  # UFW is present on Vultr's Ubuntu image. Its later INPUT chain must also admit this one route.
  ufw allow in on latch-br0 proto tcp from 172.29.240.0/24 to 172.29.240.1 port 3128 \
    comment 'Latch isolated browser to reviewed proxy'
fi
systemctl daemon-reload
systemctl enable latch-network.service latch-egress.service
systemctl restart latch-network.service latch-egress.service
systemctl is-active latch-network.service latch-egress.service
