#!/usr/bin/env bash
# Trusted operator installation on the existing worker. No new public port.
set -euo pipefail
if [[ $EUID -ne 0 ]] || [[ $(hostname -s) != latch-worker ]]; then
  printf '%s\n' 'Root on the dedicated latch-worker is required.' >&2
  exit 1
fi
cd /opt/latch
umask 077
if ! id latch-supervisor >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --shell /usr/sbin/nologin latch-supervisor
fi
usermod -aG docker latch-supervisor
# Permit service traversal only; each child directory/file retains its private owner/group.
chmod 0751 /var/lib/latch
install -d -m 0700 -o latch-supervisor -g latch-supervisor /var/lib/latch/tasks
install -d -m 0750 -o root -g latch-supervisor /var/lib/latch/supervisor-tls
LATCH_TLS=/var/lib/latch/supervisor-tls
if [[ ! -f $LATCH_TLS/ca.crt ]]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$LATCH_TLS/ca.key" -out "$LATCH_TLS/ca.crt" -days 90 \
    -subj '/CN=Latch task channel CA' -addext 'basicConstraints=critical,CA:TRUE' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' 2>/dev/null
fi
for LATCH_ROLE in server runner; do
  if [[ ! -f $LATCH_TLS/$LATCH_ROLE.crt ]]; then
    openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
      -keyout "$LATCH_TLS/$LATCH_ROLE.key" -out "$LATCH_TLS/$LATCH_ROLE.csr" \
      -subj "/CN=Latch $LATCH_ROLE" 2>/dev/null
    if [[ $LATCH_ROLE == server ]]; then
      printf '%s\n' 'subjectAltName=IP:127.0.0.1,DNS:localhost' 'extendedKeyUsage=serverAuth' > "$LATCH_TLS/extensions"
    else
      printf '%s\n' 'subjectAltName=URI:urn:latch:runner' 'extendedKeyUsage=clientAuth' > "$LATCH_TLS/extensions"
    fi
    openssl x509 -req -in "$LATCH_TLS/$LATCH_ROLE.csr" -CA "$LATCH_TLS/ca.crt" \
      -CAkey "$LATCH_TLS/ca.key" -CAcreateserial -out "$LATCH_TLS/$LATCH_ROLE.crt" \
      -days 30 -extfile "$LATCH_TLS/extensions" 2>/dev/null
  fi
done
chown root:latch-supervisor "$LATCH_TLS/ca.crt" "$LATCH_TLS/server.crt" "$LATCH_TLS/server.key"
chmod 0640 "$LATCH_TLS/ca.crt" "$LATCH_TLS/server.crt" "$LATCH_TLS/server.key"
chmod 0600 "$LATCH_TLS/ca.key"
if [[ -f $LATCH_TLS/runner.key ]]; then
  chmod 0600 "$LATCH_TLS/runner.key"
fi
chown root:latch-supervisor /var/lib/latch/supervisor.json
chmod 0640 /var/lib/latch/supervisor.json
install -m 0644 infra/worker/latch-supervisor.service infra/worker/latch-sweep.service \
  infra/worker/latch-sweep.timer /etc/systemd/system/
# linuxuser can forward only this loopback task endpoint; no remote forwards.
cat > /etc/ssh/sshd_config.d/00-latch-worker.conf <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
AllowUsers linuxuser
X11Forwarding no
AllowTcpForwarding local
PermitOpen 127.0.0.1:9443
PermitListen none
SSH
# Preserve the separately provisioned, restricted production control channel.
if id latch-tunnel >/dev/null 2>&1; then
  sed -i 's/^AllowUsers linuxuser$/AllowUsers linuxuser latch-tunnel/' /etc/ssh/sshd_config.d/00-latch-worker.conf
fi
rm -f /etc/ssh/sshd_config.d/00-latch.conf
sshd -t
systemctl reload ssh
systemctl daemon-reload
systemctl reset-failed latch-supervisor.service latch-sweep.service
systemctl enable --now latch-supervisor.service latch-sweep.timer
systemctl is-active latch-supervisor.service latch-sweep.timer
