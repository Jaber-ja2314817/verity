import { Link, NavLink, Route, Routes } from "react-router-dom";
import Footer from "./components/Footer";
import Benchmark from "./pages/Benchmark";
import CheckPage from "./pages/CheckPage";
import Home from "./pages/Home";
import HowItWorks from "./pages/HowItWorks";
import NotFound from "./pages/NotFound";

function Header() {
  const nav = ({ isActive }: { isActive: boolean }) =>
    `text-sm transition-colors ${isActive ? "text-ink" : "text-muted hover:text-ink"}`;
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
      <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <span aria-hidden className="grid h-7 w-7 place-items-center rounded-md bg-accent text-white">
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="3">
            <path d="M5 12.5l4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        Verity
      </Link>
      <nav className="flex gap-5">
        <NavLink to="/how-it-works" className={nav}>
          How it works
        </NavLink>
        <NavLink to="/benchmark" className={nav}>
          Benchmark
        </NavLink>
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/c/:id" element={<CheckPage />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/benchmark" element={<Benchmark />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
