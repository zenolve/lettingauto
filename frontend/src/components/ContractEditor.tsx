import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Table from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

import { MergeField } from "./mergeFieldMark";

type Props = {
  initialHtml: string;
  onChange: (html: string) => void;
};

export type EditorHandle = {
  insertMergeField: (key: string, value?: string) => void;
  /** Insert a plain {{token}} (no value, no mark) — for base-template editing,
   *  where the saved template must keep raw tokens for later interpolation. */
  insertToken: (key: string) => void;
};

/**
 * A docx-like contract editor. Uses Tiptap (ProseMirror) under the hood.
 * Merge tokens are rendered as styled inline spans like `{{landlord_full_name}}`.
 */
export function ContractEditor({ initialHtml, onChange, editorRef, onSelectMergeField }: Props & {
  editorRef?: (handle: EditorHandle) => void;
  /** Called with the attribute key when a merge value is Ctrl/Cmd-clicked. */
  onSelectMergeField?: (key: string) => void;
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Underline,
      // autolink OFF: otherwise TipTap wraps signature markers like
      // "/pg_sig1/" in an <a> tag, which breaks the backend's literal-string
      // substitution. The backend also defensively unwraps these, but keeping
      // them plain text from the start is cleaner.
      Link.configure({ openOnClick: false, autolink: false }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Placeholder.configure({ placeholder: "Start typing the contract…" }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      MergeField,
    ],
    content: initialHtml,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  });

  useEffect(() => {
    if (editor && editorRef) {
      editorRef({
        insertMergeField: (key, value) => {
          // Insert the RESOLVED VALUE (highlighted + traceable) when we know it,
          // falling back to the {{token}} only when there's no value yet — the
          // backend fills those at render time. Either way it carries the key,
          // so it stays hover / Ctrl-click traceable.
          const text = value != null && value !== "" ? value : `{{${key}}}`;
          editor.chain().focus().insertContent({
            type: "text",
            text,
            marks: [{ type: "mergeField", attrs: { key } }],
          }).run();
        },
        insertToken: (key) => {
          editor.chain().focus().insertContent(`{{${key}}}`).run();
        },
      });
    }
  }, [editor, editorRef]);

  // Ctrl/Cmd-click a highlighted merge value → surface its attribute name.
  useEffect(() => {
    if (!editor) return;
    const dom = editor.view.dom as HTMLElement;
    const onClick = (e: MouseEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const el = (e.target as HTMLElement).closest("[data-merge-key]") as HTMLElement | null;
      if (el) {
        e.preventDefault();
        onSelectMergeField?.(el.getAttribute("data-merge-key") || "");
      }
    };
    dom.addEventListener("mousedown", onClick);
    return () => dom.removeEventListener("mousedown", onClick);
  }, [editor, onSelectMergeField]);

  if (!editor) return null;

  return (
    <div className="editor-paper">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  );
}

function Toolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;
  const Btn = ({ on, active, label }: { on: () => void; active?: boolean; label: string }) => (
    <button
      type="button"
      onClick={on}
      className={`px-2 py-1 rounded text-sm ${active ? "bg-navy-100 text-navy-700" : "text-slate-700 hover:bg-slate-100"}`}>
      {label}
    </button>
  );
  return (
    <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-3 py-1.5 flex flex-wrap items-center gap-1">
      <Btn label="B"  on={() => editor.chain().focus().toggleBold().run()}   active={editor.isActive("bold")} />
      <Btn label="I"  on={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive("italic")} />
      <Btn label="U"  on={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive("underline")} />
      <div className="w-px h-5 bg-slate-200 mx-1" />
      <Btn label="H1" on={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive("heading", { level: 1 })} />
      <Btn label="H2" on={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive("heading", { level: 2 })} />
      <Btn label="H3" on={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} active={editor.isActive("heading", { level: 3 })} />
      <div className="w-px h-5 bg-slate-200 mx-1" />
      <Btn label="• List"   on={() => editor.chain().focus().toggleBulletList().run()}   active={editor.isActive("bulletList")} />
      <Btn label="1. List"  on={() => editor.chain().focus().toggleOrderedList().run()}  active={editor.isActive("orderedList")} />
      <Btn label="“Quote"   on={() => editor.chain().focus().toggleBlockquote().run()}   active={editor.isActive("blockquote")} />
      <div className="w-px h-5 bg-slate-200 mx-1" />
      <Btn label="Left"   on={() => editor.chain().focus().setTextAlign("left").run()} />
      <Btn label="Centre" on={() => editor.chain().focus().setTextAlign("center").run()} />
      <Btn label="Right"  on={() => editor.chain().focus().setTextAlign("right").run()} />
      <div className="w-px h-5 bg-slate-200 mx-1" />
      <Btn label="Table" on={() => editor.chain().focus().insertTable({ rows: 3, cols: 2, withHeaderRow: true }).run()} />
      <Btn label="Row +" on={() => editor.chain().focus().addRowAfter().run()} />
      <Btn label="Col +" on={() => editor.chain().focus().addColumnAfter().run()} />
      <div className="w-px h-5 bg-slate-200 mx-1" />
      <Btn label="Undo" on={() => editor.chain().focus().undo().run()} />
      <Btn label="Redo" on={() => editor.chain().focus().redo().run()} />
    </div>
  );
}
