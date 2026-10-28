# Password-breach fixture TLS

These files are public test credentials for the private integration network. They grant no deployment authority. The fixture's private key is deliberately checked in so the existing non-root test image can serve HTTPS without another runtime or certificate-generation dependency.

Kratos calls `https://password-breaches:8443/range/{prefix}`. Only the test Kratos containers and explicit fixture clients trust this CA. Certificate verification and hostname verification remain enabled. The server certificate names only `password-breaches`, and both certificates expire on 25 October 2036.

The fixture returns a single breach for the public test password defined in `tests/support/password_breaches.py`. Other passwords have no listed breaches. Lookup observations retain only five-character SHA-1 prefixes and counts. No submitted password or real breach database is stored or fetched.

## Regenerate the certificates

Run the following from the repository root with OpenSSL 3. Replace the complete certificate set together, then rerun the real Kratos breach-lookup tests. The CA signing key is temporary and is not committed. Keep `server.key` readable by the non-root test container because it is a public fixture.

```bash
fixture_dir=apps/backend/tests/fixtures/password-breaches
test_ca_dir="$(mktemp -d)"
trap 'rm -rf "$test_ca_dir"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -subj '/CN=Inframeld public test CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -keyout "$test_ca_dir/ca.key" -out "$fixture_dir/ca.pem"
openssl req -new -newkey rsa:2048 -nodes \
  -subj '/CN=password-breaches' \
  -keyout "$fixture_dir/server.key" -out "$test_ca_dir/server.csr"
cat > "$test_ca_dir/extensions.cnf" <<'EOF'
subjectAltName=DNS:password-breaches
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in "$test_ca_dir/server.csr" \
  -CA "$fixture_dir/ca.pem" -CAkey "$test_ca_dir/ca.key" \
  -set_serial 2 -days 3650 -extfile "$test_ca_dir/extensions.cnf" \
  -out "$fixture_dir/server.pem"
chmod 644 "$fixture_dir/server.key"
openssl verify -CAfile "$fixture_dir/ca.pem" "$fixture_dir/server.pem"
openssl x509 -in "$fixture_dir/server.pem" -noout -dates -ext subjectAltName
```

Update the expiry date above after regeneration. Run:

```bash
pnpm test:integration tests/integration/kratos/test_password_breach_lookup.py
```
