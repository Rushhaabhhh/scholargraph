'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useEffect,useRef,useState} from 'react';
import {Brand} from './Brand';
import {Icon} from './Icon';

export function AppLayout({children}:{children:React.ReactNode}){
 const pathname=usePathname();const [collapsed,setCollapsed]=useState(false);const [drawer,setDrawer]=useState(false);const menuButton=useRef<HTMLButtonElement>(null);const drawerClose=useRef<HTMLButtonElement>(null);const wasOpen=useRef(false);
 useEffect(()=>{if(drawer)drawerClose.current?.focus();else if(wasOpen.current)menuButton.current?.focus();wasOpen.current=drawer},[drawer]);
 useEffect(()=>{const resize=()=>{if(window.innerWidth<=700){setCollapsed(false);setDrawer(false)}};window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize)},[]);
 const items=[{href:'/#search',label:'Find researchers',icon:'search' as const},{href:'/chat',label:'Conversations',icon:'message' as const},{href:'/shortlist',label:'Shortlist',icon:'bookmark' as const},{href:'/settings',label:'Session settings',icon:'settings' as const}];
 const nav=<><div className="side-brand"><Brand/><button className="collapse-button" onClick={()=>setCollapsed(v=>!v)} aria-label={collapsed?'Expand sidebar':'Collapse sidebar'}>{collapsed?'›':'‹'}</button></div><nav className="side-nav" aria-label="Main navigation">{items.map(item=>{const active=item.href.includes('#')?(pathname==='/'||pathname.startsWith('/experts/')):pathname===item.href||pathname.startsWith(item.href);return <Link key={item.href} href={item.href} onClick={()=>setDrawer(false)} className={`nav-item ${active?'active':''}`} aria-current={active?'page':undefined}><Icon name={item.icon} size={20}/>{!collapsed&&<span>{item.label}</span>}</Link>})}</nav></>;
 return <div className={`app-shell ${collapsed?'sidebar-collapsed':''}`}><aside className="sidebar">{nav}</aside>{drawer&&<div className="drawer-scrim" onClick={()=>setDrawer(false)}><aside className="mobile-drawer" role="dialog" aria-modal="true" aria-label="Main navigation" onClick={e=>e.stopPropagation()} onKeyDown={e=>{if(e.key==='Escape')setDrawer(false);if(e.key==='Tab'){const els=Array.from(e.currentTarget.querySelectorAll<HTMLElement>('a,button:not([disabled])'));const first=els[0],last=els.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}}><button ref={drawerClose} className="drawer-close" aria-label="Close navigation" onClick={()=>setDrawer(false)}>×</button>{nav}</aside></div>}<div className="app-main"><header className="mobile-topbar"><button ref={menuButton} className="mobile-menu" aria-label="Open navigation" onClick={()=>setDrawer(true)}><Icon name="menu" size={21}/></button><Brand/></header><div className="page-content">{children}</div></div></div>
}
