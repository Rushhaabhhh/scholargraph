import Link from 'next/link';
export function Brand() { return <Link className="brand" href="/" aria-label="HireSense home"><span className="brand-mark">✳</span><span>hire<span className="brand-bold">sense</span><span className="brand-dot">.</span></span></Link>; }
export function Header() { return <header className="header"><div className="header-inner"><Brand/><div className="header-right"><span className="header-divider"/><span className="header-label">RESEARCH INTELLIGENCE</span><span className="header-tag"><i/> DBLP DATA</span></div></div></header>; }
