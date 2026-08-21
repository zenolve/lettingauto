import { Mark, mergeAttributes } from "@tiptap/core";

/**
 * Inline mark applied to every interpolated merge value so each value stays
 * traceable to the attribute it came from — even after `{{phone_number}}` has
 * been replaced by the real value like "+44…".
 *
 * Renders as:
 *   <span class="merge-field" data-merge-key="phone_number" title="phone_number">+44…</span>
 *
 * - Hovering shows the attribute name (native tooltip via `title`).
 * - Ctrl/Cmd-clicking is picked up by ContractEditor, which reads `data-merge-key`
 *   and surfaces it as the "selected attribute" in the side panel.
 *
 * The mark is a normal inline mark, so the value text underneath stays editable
 * (an agent can override a merged value inline and it still points at its field).
 * When the document is sent, the span serialises with the value inside it; the
 * backend only ever re-interpolates literal `{{token}}` text, so this is inert
 * for rendering.
 */
export const MergeField = Mark.create({
  name: "mergeField",
  // Don't extend the mark when the caret sits at its edge and the user types.
  inclusive: false,

  addAttributes() {
    return {
      key: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-merge-key"),
        renderHTML: (attrs) => (attrs.key ? { "data-merge-key": attrs.key } : {}),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-merge-key]" }];
  },

  renderHTML({ mark, HTMLAttributes }) {
    const key = (mark.attrs.key as string) ?? "";
    return [
      "span",
      mergeAttributes(HTMLAttributes, { class: "merge-field", title: key }),
      0,
    ];
  },
});
