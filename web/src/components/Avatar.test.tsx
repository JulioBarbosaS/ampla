import { fireEvent, render, screen } from "@testing-library/react";
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
  afterEach(() => useAvatarStore.setState({ version: {}, present: {} }));

  it("renders an <img> pointing at the user's avatar endpoint", () => {
    const { container } = render(<Avatar user={USER} alt="Foto de perfil" />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toContain("/api/users/7/avatar");
  });

  it("falls back to the initial when the image fails to load", () => {
    const { container } = render(<Avatar user={USER} />);
    const img = container.querySelector("img");
    if (img) fireEvent.error(img);
    expect(screen.getByText("J")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("records presence in the store from the load result", () => {
    const { container } = render(<Avatar user={USER} />);
    const img = container.querySelector("img");
    if (img) fireEvent.load(img);
    expect(useAvatarStore.getState().present[7]).toBe(true);
  });

  it("shows '?' for a missing user", () => {
    render(<Avatar user={null} />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });
});
