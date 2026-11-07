import { fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { mockFetch } from "./mockApi";
import { renderApp } from "./render";

beforeEach(() => {
  localStorage.clear();
  mockFetch();
});

describe("navigation", () => {
  it("renders the overview with model configuration and recent runs", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(await screen.findByText("synthetic.pdf")).toBeInTheDocument();
    expect((await screen.findAllByText("llama-3.3-70b-versatile")).length).toBeGreaterThan(0);
  });

  it("navigates to every page from the sidebar", async () => {
    renderApp("/");
    const nav = screen.getAllByRole("navigation")[0];
    const pages: [string, string][] = [
      ["Requirement Studio", "Requirement Studio"],
      ["Prompt Engineering", "Prompt Engineering Studio"],
      ["Document Workspace", "Document Workspace"],
      ["Competition Arena", "Model Competition Arena"],
      ["Results Comparison", "Results Comparison"],
      ["Evaluation", "Evaluation"],
      ["Export Center", "Export Center"],
    ];
    for (const [link, heading] of pages) {
      fireEvent.click(within(nav).getByRole("link", { name: new RegExp(link) }));
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    }
  });

  it("shows a not-found page for unknown routes", async () => {
    renderApp("/nope");
    expect(await screen.findByText("This page doesn't exist")).toBeInTheDocument();
  });
});

describe("competition arena", () => {
  it("renders the 3 × 3 matrix from live status", async () => {
    renderApp("/arena");
    const cells = await screen.findAllByRole("button", { name: /prompt on M\d/ });
    expect(cells).toHaveLength(9);
    expect(screen.getByRole("button", { name: "P3 prompt on M3: failed" })).toBeInTheDocument();
    expect(screen.getAllByText("83%")).toHaveLength(8);
    expect(screen.getByText(/isn't accuracy/)).toBeInTheDocument();
  });
});
