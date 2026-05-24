/**
 * Tests for the SatisfactionPrompt overlay.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import {
  SatisfactionPrompt,
  type SatisfactionOption,
} from "./SatisfactionPrompt";

const OPTIONS: SatisfactionOption[] = [
  {
    key: "crystal_clear",
    label: "Crystal clear",
    description: "Let's keep going.",
  },
  {
    key: "counter_doubt",
    label: "Have a counter-doubt",
    description: "I want to ask another question.",
  },
  {
    key: "somewhat_cleared",
    label: "Somewhat cleared",
    description: "Some parts are still fuzzy.",
  },
  {
    key: "start_over",
    label: "Start over",
    description: "Try a different angle.",
  },
];

describe("SatisfactionPrompt", () => {
  it("renders the title + all four options", () => {
    const { getByText } = render(
      <SatisfactionPrompt options={OPTIONS} onChoose={() => {}} />,
    );
    expect(getByText(/How clear was that/i)).toBeTruthy();
    for (const opt of OPTIONS) {
      expect(getByText(opt.label)).toBeTruthy();
      expect(getByText(opt.description)).toBeTruthy();
    }
  });

  it("the first option is styled as primary, the rest secondary", () => {
    const { getByTestId } = render(
      <SatisfactionPrompt options={OPTIONS} onChoose={() => {}} />,
    );
    expect(
      getByTestId("satisfaction-option-crystal_clear").getAttribute(
        "data-variant",
      ),
    ).toBe("primary");
    expect(
      getByTestId("satisfaction-option-counter_doubt").getAttribute(
        "data-variant",
      ),
    ).toBe("secondary");
  });

  it("invokes onChoose with the correct key for each option", () => {
    const onChoose = vi.fn();
    const { getByTestId } = render(
      <SatisfactionPrompt options={OPTIONS} onChoose={onChoose} />,
    );
    fireEvent.click(getByTestId("satisfaction-option-crystal_clear"));
    fireEvent.click(getByTestId("satisfaction-option-counter_doubt"));
    fireEvent.click(getByTestId("satisfaction-option-somewhat_cleared"));
    fireEvent.click(getByTestId("satisfaction-option-start_over"));
    expect(onChoose).toHaveBeenCalledTimes(4);
    expect(onChoose).toHaveBeenNthCalledWith(1, "crystal_clear");
    expect(onChoose).toHaveBeenNthCalledWith(2, "counter_doubt");
    expect(onChoose).toHaveBeenNthCalledWith(3, "somewhat_cleared");
    expect(onChoose).toHaveBeenNthCalledWith(4, "start_over");
  });

  it("renders with role=dialog for accessibility", () => {
    const { getByRole } = render(
      <SatisfactionPrompt options={OPTIONS} onChoose={() => {}} />,
    );
    expect(getByRole("dialog")).toBeTruthy();
  });
});
