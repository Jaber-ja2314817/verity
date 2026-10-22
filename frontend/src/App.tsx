import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigationType } from "react-router-dom";
import Footer from "./components/Footer";
import Benchmark from "./pages/Benchmark";
import CheckPage from "./pages/CheckPage";
import Home from "./pages/Home";
import HowItWorks from "./pages/HowItWorks";
import NotFound from "./pages/NotFound";

function Header() {
  const nav = ({ isActive }: { isActive: boolean }) =>
    `transition-colors ${isActive ? "text-accent" : "text-muted hover:text-ink"}`;
  return (
    <header className="mx-auto w-full max-w-[60rem] px-4 pt-8 sm:px-12">
      <div className="flex items-center justify-between gap-6 border-b border-rule/80 pb-5">
        <Link to="/" className="flex items-center gap-6">
          <span className="font-serif text-[2.3rem] font-light leading-none tracking-[-0.02em]">verity.</span>
          <span aria-hidden className="hidden h-10 w-px bg-line sm:block" />
          <span className="hidden text-[13px] leading-snug text-muted sm:block">
            An evidence
            <br />
            investigation desk
          </span>
        </Link>
        <nav aria-label="Main" className="eyebrow flex shrink-0 gap-2 whitespace-nowrap text-muted">
          <NavLink to="/how-it-works" className={nav}>
            How it works
          </NavLink>
          <span aria-hidden>/</span>
          <NavLink to="/benchmark" className={nav}>
            Benchmark
          </NavLink>
        </nav>
      </div>
      <div className="eyebrow flex justify-between gap-4 pt-3 text-muted">
        <p>Question carefully. Follow the evidence.</p>
        <p className="hidden sm:block">Evidence desk · Two-model jury</p>
      </div>
    </header>
  );
}

/** BrowserRouter keeps the old scroll position on navigation; start new pages at the top. */
function ScrollToTop() {
  const { pathname } = useLocation();
  const navType = useNavigationType();
  useEffect(() => {
    if (navType !== "POP") window.scrollTo(0, 0); // back/forward: let the browser restore
  }, [pathname, navType]);
  return null;
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col sm:m-1.5 sm:min-h-[calc(100vh-0.75rem)] bg-paper">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:text-on-accent"
      >
        Skip to content
      </a>
      <ScrollToTop />
      <Header />
      <main id="main" tabIndex={-1} className="focus:outline-none mx-auto w-full max-w-[60rem] flex-1 px-4 pt-10 pb-16 sm:px-12">
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
