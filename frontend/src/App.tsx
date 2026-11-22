import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router";
import { Header } from "./components/Header";
import { AnalysisScreen } from "./screens/AnalysisScreen";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ReportScreen } from "./screens/ReportScreen";
import { SimulationScreen } from "./screens/SimulationScreen";
import { StartScreen } from "./screens/StartScreen";

function NotFound() {
  return (
    <div className="screen screen-text">
      <h1>Nie ma takiej strony</h1>
      <Link to="/" className="button button-primary button-large">
        Przejdź do strony startowej
      </Link>
    </div>
  );
}

export function App() {
  const { pathname } = useLocation();
  // The effect must return nothing: in newer browsers scrollTo returns a Promise,
  // which React would take for the cleanup and fail to call.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <div className="page">
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<StartScreen />} />
          <Route path="/analiza/:reportId" element={<AnalysisScreen />} />
          <Route path="/raport/:reportId" element={<ReportScreen />} />
          <Route path="/raport/:reportId/historia" element={<HistoryScreen />} />
          <Route path="/raport/:reportId/symulacja" element={<SimulationScreen />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
