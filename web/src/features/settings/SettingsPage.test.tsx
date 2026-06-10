import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { useAvatarStore } from "../../stores/avatar";
import { SettingsPage } from "./SettingsPage";

// Stub the cropper UI: fire onCropComplete on mount so "Salvar" is enabled, and
// resolve the crop to a fixed data URL — the real canvas/cropper need a browser.
vi.mock("react-easy-crop", async () => {
  const React = await import("react");
  return {
    default: ({ onCropComplete }: { onCropComplete?: (a: unknown, b: unknown) => void }) => {
      React.useEffect(() => {
        onCropComplete?.({}, { x: 0, y: 0, width: 100, height: 100 });
      }, [onCropComplete]);
      return React.createElement("div", { "data-testid": "cropper" });
    },
  };
});

vi.mock("../../lib/crop", async (orig) => ({
  ...(await orig<typeof import("../../lib/crop")>()),
  getCroppedImage: vi.fn().mockResolvedValue("data:image/jpeg;base64,CROPPED"),
}));

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 7, email: "julio@example.com", name: "Julio", role: "admin", created_at: "" },
  });
  useAvatarStore.setState({ photos: {} });
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

  it("crops a picked image and saves it to the avatar store", async () => {
    render(<SettingsPage />);
    const input = screen.getByLabelText("Selecionar foto");
    const file = new File(["PNG"], "me.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await screen.findByRole("dialog", { name: "Recortar foto" });
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(useAvatarStore.getState().photos[7]).toBe("data:image/jpeg;base64,CROPPED"),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("removes an existing photo", async () => {
    useAvatarStore.setState({ photos: { 7: "data:image/jpeg;base64,abc" } });
    render(<SettingsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Remover foto" }));
    expect(useAvatarStore.getState().photos[7]).toBeUndefined();
  });
});
