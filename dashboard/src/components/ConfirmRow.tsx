import React from "react";
import { AppIcon } from "../icons/IconMap";

/** Cancel (arrow-left) on the left, confirm (check) on the right –
 *  the shared pattern for the small edit panels. */
export default function ConfirmRow({
  onCancel,
  onConfirm,
  disabled,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        color: "var(--color-text)",
        fontSize: "1.5rem",
      }}
    >
      <span style={{ cursor: "pointer", display: "flex" }} onClick={onCancel}>
        <AppIcon name="back" />
      </span>
      <span
        style={{
          cursor: disabled ? "default" : "pointer",
          display: "flex",
          opacity: disabled ? 0.3 : 1,
        }}
        onClick={disabled ? undefined : onConfirm}
      >
        <AppIcon name="check" />
      </span>
    </div>
  );
}
