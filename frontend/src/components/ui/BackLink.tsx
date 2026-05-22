import { Link, useNavigate } from "react-router-dom";

type Props = {
  /** Optional explicit destination — defaults to browser history back. */
  to?: string;
  label?: string;
};

/**
 * Consistent back-nav for form / editor pages. When `to` is given it renders
 * a stable destination link (preferred — survives reload / direct deep link).
 * When omitted it falls back to ``history.back()``.
 */
export function BackLink({ to, label = "Back" }: Props) {
  const nav = useNavigate();
  const baseCls = "inline-flex items-center gap-1 text-sm text-navy-600 hover:text-navy-800 hover:underline";
  if (to) {
    return <Link to={to} className={baseCls}>← {label}</Link>;
  }
  return (
    <button type="button" onClick={() => nav(-1)} className={baseCls}>← {label}</button>
  );
}
