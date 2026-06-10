import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { useAvatarStore } from "../../stores/avatar";
import { SettingsPage } from "./SettingsPage";

vi.mock("../../lib/api/auth", () => ({
  authApi: {
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
    setAvatar: vi.fn(),
    removeAvatar: vi.fn(),
  },
}));

import { authApi } from "../../lib/api/auth";

// Stub the cropper UI: render children (so the <img> ref mounts) and fire
// onComplete so "Salvar" is enabled — the real canvas/cropper need a browser.
vi.mock("react-image-crop", async () => {
  const React = await import("react");
  return {
    default: ({
      children,
      onComplete,
    }: {
      children?: ReactNode;
      onComplete?: (c: unknown) => void;
    }) => {
      React.useEffect(() => {
        onComplete?.({ x: 0, y: 0, width: 50, height: 50, unit: "px" });
      }, [onComplete]);
      return React.createElement("div", { "data-testid": "cropper" }, children);
    },
    centerCrop: (c: unknown) => c,
    makeAspectCrop: (c: unknown) => c,
  };
});

vi.mock("../../lib/crop", async (orig) => ({
  ...(await orig<typeof import("../../lib/crop")>()),
  getCroppedImage: vi.fn().mockReturnValue("data:image/jpeg;base64,CROPPED"),
}));

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 7, email: "julio@example.com", name: "Julio", role: "admin", created_at: "" },
  });
  useAvatarStore.setState({ version: {}, present: {} });
});

afterEach(() => {
  useAuthStore.setState({ user: null });
  localStorage.clear();
});

describe("SettingsPage photo", () => {
  it("rejects a non-image file", async () => {
    render(<SettingsPage />);
    const input = screen.getByLabelText("Selecionar foto");
    const file = new File(["nope"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Selecione um arquivo de imagem.");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("crops a picked image and uploads it to the hub", async () => {
    vi.mocked(authApi.setAvatar).mockResolvedValue(null);
    render(<SettingsPage />);
    const input = screen.getByLabelText("Selecionar foto");
    const file = new File(["PNG"], "me.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    const dialog = await screen.findByRole("dialog", { name: "Recortar foto" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(authApi.setAvatar).toHaveBeenCalledWith("data:image/jpeg;base64,CROPPED"),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("removes an existing photo via the API", async () => {
    vi.mocked(authApi.removeAvatar).mockResolvedValue(null);
    useAvatarStore.setState({ present: { 7: true } }); // a photo is present
    render(<SettingsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Remover foto" }));
    expect(authApi.removeAvatar).toHaveBeenCalled();
  });
});

describe("SettingsPage profile", () => {
  it("disables Salvar until the name changes", () => {
    render(<SettingsPage />);
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  it("saves an edited name and updates the auth store", async () => {
    vi.mocked(authApi.updateProfile).mockResolvedValue({
      id: 7,
      email: "julio@example.com",
      name: "Julio B",
      role: "admin",
      created_at: "",
    });
    render(<SettingsPage />);
    const nameInput = screen.getByLabelText("Nome");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Julio B");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(authApi.updateProfile).toHaveBeenCalledWith({ name: "Julio B" }));
    expect(useAuthStore.getState().user?.name).toBe("Julio B");
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
  });
});

beforeEach(() => {
  vi.mocked(authApi.updateProfile).mockReset();
  vi.mocked(authApi.changePassword).mockReset();
  vi.mocked(authApi.setAvatar).mockReset();
  vi.mocked(authApi.removeAvatar).mockReset();
});

describe("SettingsPage password", () => {
  it("validates and submits a password change", async () => {
    vi.mocked(authApi.changePassword).mockResolvedValue(null);
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText("Senha atual"), "senha-atual-1");
    await userEvent.type(screen.getByLabelText("Nova senha"), "nova-senha-segura-9");
    await userEvent.type(screen.getByLabelText("Confirmar nova senha"), "nova-senha-segura-9");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));

    await waitFor(() =>
      expect(authApi.changePassword).toHaveBeenCalledWith({
        current_password: "senha-atual-1",
        new_password: "nova-senha-segura-9",
      }),
    );
    expect(await screen.findByText("Senha alterada.")).toBeInTheDocument();
  });

  it("rejects a mismatched confirmation without calling the API", async () => {
    render(<SettingsPage />);
    await userEvent.type(screen.getByLabelText("Senha atual"), "senha-atual-1");
    await userEvent.type(screen.getByLabelText("Nova senha"), "nova-senha-segura-9");
    await userEvent.type(screen.getByLabelText("Confirmar nova senha"), "diferente-99999");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/não confere/);
    expect(authApi.changePassword).not.toHaveBeenCalled();
  });
});
