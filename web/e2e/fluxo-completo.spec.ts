import { expect, test } from "@playwright/test";

/**
 * End-to-end flow against the real hub: admin setup → agent creation
 * → key generation → conversation via the panel (perspective + send).
 * The tests are sequential — the database is reset once at the start of the run.
 */
test.describe.configure({ mode: "serial" });

test("administrator setup on first access", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Criar conta de administrador" })).toBeVisible();

  await page.getByLabel("Nome").fill("Julio Admin");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel(/Senha/).fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Criar conta admin" }).click();

  // logged in: app shell with navigation and the account (avatar) entry point
  await expect(page.getByRole("link", { name: "Conversas" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Configurações" })).toBeVisible();
});

test("login, agent creation and daemon key", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  await page.getByRole("link", { name: "Meus agentes" }).click();

  // two agents to talk to each other
  for (const [slug, display] of [
    ["backend-julio", "Backend do Julio"],
    ["mobile-eduardo", "Mobile do Eduardo"],
  ] as const) {
    await page.getByLabel(/Slug/).fill(slug);
    await page.getByLabel("Nome de exibição").fill(display);
    await page.getByRole("button", { name: "Criar", exact: true }).click();
    await expect(page.getByRole("heading", { name: slug })).toBeVisible();
  }

  // key shown only once, with the amp_ prefix
  await page
    .locator("section", { hasText: "backend-julio" })
    .getByRole("button", { name: "Gerar chave" })
    .first()
    .click();
  await expect(page.getByText(/^amp_[0-9a-f]{64}$/)).toBeVisible();
});

test("conversation via the panel: perspective, send and pending bubble", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  // perspective selected automatically (the user's first agent)
  await expect(page.getByLabel("Conversando como")).toHaveValue("backend-julio");

  // select the partner and send
  await page.getByRole("button", { name: /mobile-eduardo/ }).click();
  const composer = page.getByPlaceholder(/Mensagem para mobile-eduardo/);
  await composer.fill("Existe endpoint de reset de senha?");
  await page.getByRole("button", { name: "Enviar" }).click();

  // bubble appears; recipient offline → pending. The message also becomes a
  // preview in the sidebar (a <span>), so we target the chat bubble (a <p>).
  const bubble = page
    .getByRole("paragraph")
    .filter({ hasText: "Existe endpoint de reset de senha?" });
  await expect(bubble).toBeVisible();
  await expect(page.getByText(/pendente/)).toBeVisible();

  // history persists after reload
  await page.reload();
  await page.getByRole("button", { name: /mobile-eduardo/ }).click();
  await expect(
    page.getByRole("paragraph").filter({ hasText: "Existe endpoint de reset de senha?" }),
  ).toBeVisible();
});

test("offline agent appears with offline presence in the sidebar", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("julio@example.com");
  await page.getByLabel("Senha").fill("senha-muito-segura-1");
  await page.getByRole("button", { name: "Entrar" }).click();

  const entry = page.getByRole("button", { name: /mobile-eduardo/ });
  await expect(entry.getByLabel("offline")).toBeVisible();
});
