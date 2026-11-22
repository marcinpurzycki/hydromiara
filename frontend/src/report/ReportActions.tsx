import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Icon } from "../components/Icon";

interface Props {
  allOpen: boolean;
  onToggleAll: () => void;
  onPrint: () => void;
  /** Makes the PDF file; rejects when the file could not be made. */
  onPdf: () => Promise<void>;
}

/** Print, PDF file, link to the Report, expand all, start over. */
export function ReportActions({ allOpen, onToggleAll, onPrint, onPdf }: Props) {
  const navigate = useNavigate();
  const [linkShown, setLinkShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pdf, setPdf] = useState<"idle" | "working" | "failed">("idle");

  const savePdf = async () => {
    setPdf("working");
    try {
      await onPdf();
      setPdf("idle");
    } catch {
      setPdf("failed");
    }
  };
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const url = window.location.href;

  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!confirming) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setConfirming(false);
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [confirming]);

  const copyLink = async () => {
    setLinkShown(true);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2500);
    } catch {
      // No clipboard access: the address stays in the field to copy by hand.
    }
  };

  return (
    <>
      {linkShown && (
        <div className="link-row card no-print">
          <label htmlFor="report-link">Link do raportu</label>
          <input
            id="report-link"
            type="text"
            readOnly
            value={url}
            onFocus={(event) => event.target.select()}
            onClick={(event) => event.currentTarget.select()}
          />
          <span className="link-status" role="status">
            {copied ? "Skopiowano do schowka" : ""}
          </span>
        </div>
      )}
      {pdf === "failed" && (
        <p className="field-error no-print" role="alert">
          Nie udało się utworzyć pliku PDF. Użyj przycisku „Drukuj raport” i wybierz w oknie drukowania zapis do PDF.
        </p>
      )}
      <div className="button-row no-print">
        <button type="button" className="button button-primary" onClick={onPrint}>
          <Icon name="print" size={22} />
          Drukuj raport
        </button>
        <button type="button" className="button button-soft" disabled={pdf === "working"} onClick={() => void savePdf()}>
          <Icon name="pdf" size={22} />
          {pdf === "working" ? "Tworzymy PDF…" : "Zapisz PDF"}
        </button>
        <button type="button" className="button button-soft" onClick={() => void copyLink()}>
          <Icon name="link" size={22} />
          {copied ? "Link skopiowany" : "Link do raportu"}
        </button>
        <button type="button" className="button button-soft" aria-expanded={allOpen} onClick={onToggleAll}>
          <Icon name="list" size={22} />
          {allOpen ? "Zwiń porady" : "Rozwiń wszystkie porady"}
        </button>
        <button type="button" className="button button-soft" onClick={() => setConfirming(true)}>
          <Icon name="restart" size={22} />
          Zacznij od nowa
        </button>
      </div>
      {confirming && (
        <div className="dialog-backdrop no-print" role="presentation" onClick={() => setConfirming(false)}>
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="restart-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="restart-title">Zacząć od nowa?</h2>
            <p>Bieżący raport zostanie zamknięty. Jeśli chcesz do niego wrócić, zapisz wcześniej link albo PDF.</p>
            <div className="button-row dialog-buttons">
              <button type="button" className="button button-soft" onClick={() => setConfirming(false)}>
                Anuluj
              </button>
              <button type="button" className="button button-primary" onClick={() => navigate("/")}>
                Tak, zacznij od nowa
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
