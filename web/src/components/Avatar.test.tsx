import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { User } from "../lib/api/types";
import { useAvatarStore } from "../stores/avatar";
import { Avatar } from "./Avatar";

const USER: User = {
  id: 7,
  email: "julio@example.com",
  name: "Julio",
  role: "admin",
  created_at: "",
};

describe("Avatar", () => {
  afterEach(() => {
    useAvatarStore.setState({ photos: {} });
  });

  it("falls back to the name's initial when there is no photo", () => {
    render(<Avatar user={USER} />);
    expect(screen.getByText("J")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("renders the photo when one is set for the user", () => {
    useAvatarStore.setState({ photos: { 7: "data:image/jpeg;base64,abc" } });
    render(<Avatar user={USER} alt="Foto de perfil" />);
    const img = screen.getByRole("img", { name: "Foto de perfil" });
    expect(img).toHaveAttribute("src", "data:image/jpeg;base64,abc");
  });

  it("shows '?' for a missing user", () => {
    render(<Avatar user={null} />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });
});
