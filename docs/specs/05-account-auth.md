# Epic 05 — Account & Auth

Closes the debt tracked in memory (`perfil-edicao-pendente`): the profile page is
read-only, the avatar lives only in `localStorage`, and "Esqueci minha senha" /
the social buttons are placeholders. This epic makes profile editing real and
moves the avatar server-side.

Files in play: `hub/app/schemas/auth.py`, `hub/app/services/auth_service.py`,
`hub/app/api/routes/auth.py`, `hub/app/models/user.py`, `hub/app/core/security.py`,
`hub/app/models/audit.py`, `web/src/lib/api/auth.ts`,
`web/src/features/settings/SettingsPage.tsx`, `web/src/components/Avatar.tsx`,
`web/src/stores/avatar.ts`.

---

## 5.1 Edit profile name · `◻ planned` · risk: low

**Goal.** `PATCH /api/auth/me` to update the display `name` (email stays the
login identity — out of scope for v1; changing it needs uniqueness + re-auth).

**Hub.** New schema `ProfileUpdate {name: str (1..120)}`. `auth_service.update_profile(user, name)` → set, save via `UserRepository.save`, audit `profile_updated`. Route `PATCH /api/auth/me` (authenticated) → `UserOut`.

**Web.** Un-disable the Nome field in `SettingsPage` "Dados"; add a Salvar button;
`authApi.updateProfile({name})`; on success update the auth store (`setUser`) so
the topbar/drawer reflect it immediately.

**Tests.** Service unit (rename persists + audited); integration (`PATCH /me`
authz + validation, 422 on empty/too long); openapi golden. Web: SettingsPage
edits name and updates store.

**Effort.** ~0.5 day.

---

## 5.2 Change password · `◻ planned` · risk: med (security-sensitive)

**Goal.** Authenticated password change with current-password verification.

**Hub.** Schema `PasswordChange {current_password, new_password: str (10..128)}`.
`auth_service.change_password(user, current, new)`:
- Verify `current` with `security.verify_password` against `user.password_hash`;
  wrong → `AuthError` (generic), audited `password_change_fail`.
- Hash `new` (`security.hash_password`, bcrypt cost 12), save, audit
  `password_changed`.
- **Session policy:** keep the current session valid (JWT unchanged) but document
  that other sessions remain valid until expiry (no server-side session store
  today — a "log out other devices" feature would need session tracking; note as
  future, ties to a possible sessions feature).

Route `POST /api/auth/me/password` (authenticated) → 204.

**Rate limiting.** Reuse the `auth_rate_limit` dependency (the login limiter) on
this route to blunt online guessing of the current password.

**Web.** A "Senha" section in `SettingsPage`: current + new + confirm fields,
client-side min-length + match check, `authApi.changePassword(...)`, success/error
toasts. (Replaces part of the "edição em breve" note.)

**Security.** Generic error on wrong current password (no oracle); rate-limited;
new password runs through the same min-length policy as setup/register; never log
passwords; the change is audited (event only, no secret in `detail`).

**Tests.** Service unit (correct current → changes + audited; wrong current →
error + audited, hash unchanged); integration (route authz, 422 short password,
429 under rate limit); openapi golden; web form validation + submit.

**Effort.** ~1 day.

---

## 5.3 Avatar upload (server-side) · `◻ planned` · risk: med

**Goal.** Replace the client-only localStorage avatar (Epic from earlier) with
real server storage, so the photo follows the user across devices and is visible
to others in the directory/chat.

**Storage decision.** Self-hosted, single-node, SQLite. Two options:
- **A. Blob column (recommended for v1):** store the cropped ~256px JPEG (already
  produced client-side by `lib/crop.ts`, ≤ ~50–100 KB) in a new `user_avatars`
  table (`user_id` PK, `mime`, `bytes` BLOB, `updated_at`). Simple, backed up
  with the DB, no filesystem layout. Serve via `GET /api/users/{id}/avatar`
  (cacheable with an ETag/`updated_at`).
- B. On-disk under a data dir + path in DB. More moving parts, needs volume
  mgmt; defer.

**Hub.**
- `POST /api/auth/me/avatar` (authenticated, `multipart/form-data` or a JSON data
  URL — match what the web already produces). **Re-validate server-side**: it’s
  an image, ≤ a hard byte cap (e.g. 256 KB after crop), and **re-encode through a
  server-side image step** (Pillow) to a normalized 256×256 JPEG — never trust the
  client bytes; this strips metadata and rejects non-images / decompression
  bombs (cap dimensions before decode).
- `DELETE /api/auth/me/avatar` → remove.
- `GET /api/users/{id}/avatar` → the bytes (or 404 → client falls back to
  initial). Public to authenticated users (avatars show in the directory/chat).
- Expose `avatar_updated_at` (or a bool `has_avatar`) on `UserOut` /
  `DirectoryEntry` so clients know whether to load the image (and for cache
  busting).

**Web.** `Avatar.tsx` already abstracts the source — change it to render
`/api/users/{id}/avatar?v=<updated_at>` when `has_avatar`, else the initial; drop
the `localStorage` source (keep the cropper from `AvatarCropper.tsx`, but on Save
it now `POST`s to the server instead of writing the store). Migrate/retire the
`avatar` store. `DirectoryEntry`/chat can show real photos.

**Security.** This is the riskiest item: an upload endpoint is an attack surface.
- Server-side image re-encode (Pillow) with a max-pixels guard (Pillow
  `MAX_IMAGE_PIXELS`) to stop decompression bombs; reject anything that isn’t a
  decodable image; normalize to JPEG (drops SVG/HTML/EXIF entirely — **never**
  accept SVG).
- Byte cap enforced before reading the whole body; content-type checked but not
  trusted (sniff/decode decides).
- `Content-Type: image/jpeg` + `Content-Disposition: inline` + `X-Content-Type-Options: nosniff` on serve; no user-controlled filename.
- Audited `avatar_updated` / `avatar_removed`.
- Rate-limit uploads per user.

**Dependency.** Adds **Pillow** to the hub (image re-encode). Note in the PR; it’s
a well-known, maintained lib. Keeps the decode/validate server-side rather than
trusting the browser.

**Tests.** Service/integration: a valid small JPEG is accepted + normalized;
a non-image (text/SVG/oversized/zip) is rejected; `GET` returns bytes with the
right headers; `DELETE` removes; cross-user `POST` to someone else’s avatar is
forbidden; `UserOut.has_avatar` flips. openapi golden (3 endpoints + the new
`UserOut` field). Web: cropper Save now calls the API; Avatar loads the URL and
falls back on 404.

**Effort.** ~2 days (incl. Pillow validation + serving + web swap).

---

## 5.4 Forgot-password reset · `◻ planned` · risk: med · **design constraint: no email**

**Goal.** Replace the disabled "Esqueci minha senha" placeholder with a real flow
that fits a **100% local, no-SMTP** system (ARCHITECTURE.md: "no email sending;
invites are copyable links/codes").

**Approach (admin-mediated reset, mirroring the invite model).** No email means
no self-service email link. Instead:
- **Admin-issued reset token:** an admin (Team page) clicks "Redefinir senha" for
  a user → hub creates a single-use, expiring reset token (new `password_resets`
  table: `id, user_id, token_hash (sha256), expires_at, used_at`), shows a
  **copyable link/code once** (exactly like invites). The admin hands it to the
  user out-of-band.
- The user opens `/reset?token=…`, sets a new password →
  `POST /api/auth/reset-password {token, new_password}` validates the token (hash
  lookup, not expired/used), sets the password, marks the token used, audits
  `password_reset`. Generic errors; rate-limited.
- The login page’s "Esqueci minha senha" becomes a small explainer: "peça um link
  de redefinição ao administrador" (since there’s no email) — honest to the
  architecture. (If a self-hosted operator later wires SMTP/a webhook channel, a
  self-service variant can reuse the same token table.)

**Endpoints.** `POST /api/users/{id}/password-reset` (admin-only; returns the
one-time token/link) and `POST /api/auth/reset-password` (public, token-gated).

**Web.** Team page: per-user "Redefinir senha" (admin) → modal with the copyable
link (like the invite UI). New public `ResetPasswordPage` at `/reset`. Login
footer link updated to the explainer.

**Security.** Token is high-entropy (`secrets`), stored as sha256, single-use,
short expiry; hash-lookup (no timing oracle); generic errors; rate-limited;
admin-only issuance is audited; setting a new password invalidates the token. No
secret in audit `detail`.

**Tests.** Service: issue token (admin-only); valid token resets + marks used;
expired/used/forged token rejected; audited. Integration: both endpoints +
authz + 429. openapi golden. Web: reset page happy path + invalid token.

**Effort.** ~1.5 days.

---

## Epic 05 milestone checklist

- [x] 5.1 `PATCH /api/auth/me` (name) + SettingsPage edit — `e836cdd`
- [x] 5.2 `POST /api/auth/me/password` (verify current, rate-limited) + UI — `87d2968`
- [x] 5.3 Avatar upload/serve/delete (Pillow re-encode) + web off localStorage — `5a0df42`
- [x] 5.4 Admin-mediated reset (token table + `/reset` page) — no-SMTP — `f670d2a`

**Epic 05 complete.** Profile debt closed; openapi golden + migrations
regenerated each step. Email change is intentionally still out of scope (login
identity). Avatar upload rate-limiting was deferred (auth + 2 MB cap + Pillow
bound the surface) — a follow-up if needed.
