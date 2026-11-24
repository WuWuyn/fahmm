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

it("keeps escaped pipes and backslashes inside their table cells", () => {
  const source = [
    "# Biên bản", "", "Các công việc được ghi nhận:", "",
    "| Công việc | Ghi chú |",
    "| --- | --- |",
    "| Xử lý A \\| B | C:\\\\work\\\\files |",
    "| Dấu \\\\ và \\| | A\\q |",
    "", "Nội dung tiếp theo.",
  ].join("\n");
  render(<article><MinutesMarkdown source={source} /></article>);
  expect(screen.getByText("Các công việc được ghi nhận:")).toBeTruthy();
  expect(screen.getByText("Nội dung tiếp theo.")).toBeTruthy();
  expect(screen.getByRole("cell", { name: "Xử lý A | B" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "C:\\work\\files" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "Dấu \\ và |" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "A\\q" })).toBeTruthy();
  expect(screen.getAllByRole("row")).toHaveLength(3);
  expect(screen.getAllByRole("cell")).toHaveLength(4);
});
