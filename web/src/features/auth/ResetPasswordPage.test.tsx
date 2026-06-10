import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResetPasswordPage } from "./ResetPasswordPage";

vi.mock("../../lib/api/auth", () => ({ authApi: { resetPassword: vi.fn() } }));

import { authApi } from "../../lib/api/auth";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ResetPasswordPage />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.mocked(authApi.resetPassword).mockReset());

describe("ResetPasswordPage", () => {
  it("shows an invalid-link message without a token", () => {
    renderAt("/reset");
    expect(screen.getByText(/Link inválido/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Redefinir senha" })).toBeNull();
  });

  it("resets the password with a token", async () => {
    vi.mocked(authApi.resetPassword).mockResolvedValue(null);
    renderAt("/reset?token=abc123");
    await userEvent.type(screen.getByLabelText(/Nova senha/), "senha-nova-segura-1");
    await userEvent.type(screen.getByLabelText("Confirmar nova senha"), "senha-nova-segura-1");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(authApi.resetPassword).toHaveBeenCalledWith({
      token: "abc123",
      new_password: "senha-nova-segura-1",
    });
    expect(await screen.findByText(/Sua senha foi redefinida/)).toBeInTheDocument();
  });

  it("rejects a mismatched confirmation without calling the API", async () => {
    renderAt("/reset?token=abc123");
    await userEvent.type(screen.getByLabelText(/Nova senha/), "senha-nova-segura-1");
    await userEvent.type(screen.getByLabelText("Confirmar nova senha"), "diferente-99999");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/não confere/);
    expect(authApi.resetPassword).not.toHaveBeenCalled();
  });
});
