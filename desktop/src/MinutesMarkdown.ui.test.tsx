// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MinutesMarkdown } from "@/features/minutes/MinutesMarkdown";

afterEach(cleanup);

it("renders the meeting form tables alongside headings and prose", () => {
  render(<article><MinutesMarkdown source={"# MEETING MINUTES\n\n## 1. Thông tin cuộc họp\n| Hạng mục | Nội dung |\n| --- | --- |\n| Mục tiêu | Review demo |\n\n## 2. Tóm tắt điều hành\nĐã ghi nhận."} /></article>);
  expect(screen.getByRole("heading", { name: "1. Thông tin cuộc họp" })).toBeTruthy();
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByRole("cell", { name: "Review demo" })).toBeTruthy();
  expect(screen.getByText("Đã ghi nhận.")).toBeTruthy();
});
