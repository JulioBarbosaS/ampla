import { describe, expect, it } from "vitest";
import { buildServiceUnit } from "../../src/cli/install-service.js";

describe("buildServiceUnit", () => {
  const unit = buildServiceUnit({
    agent: "backend-julio",
    nodeBin: "/usr/bin/node",
    ampScript: "/opt/amp/bridge/bin/amp.mjs",
  });

  it("runs `amp <agent> on` (tsx from src/ — always a fresh build)", () => {
    expect(unit).toContain("ExecStart=/usr/bin/node /opt/amp/bridge/bin/amp.mjs backend-julio on");
  });

  it("restarts on failure and starts on boot", () => {
    expect(unit).toContain("Restart=on-failure");
    expect(unit).toContain("WantedBy=default.target");
  });

  it("names the unit after the agent", () => {
    expect(unit).toContain("Description=Ampla daemon — backend-julio");
  });
});
