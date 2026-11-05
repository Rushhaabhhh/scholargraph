import Link from 'next/link';
import {Icon} from './Icon';
export function Brand(){return <Link className="brand" href="/#top" aria-label="ScholarGraph home"><span className="brand-mark"><Icon name="graph" size={20}/></span><span>scholar<span className="brand-strong">graph</span><span className="brand-period">.</span></span></Link>}
