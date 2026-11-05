import {api} from './api';
import type {Memory} from './types';
export const SESSION_KEY='hiresense-session';
export type SessionInfo={session_id:string;memory:Memory};
export async function getSession():Promise<SessionInfo>{
 let id=typeof window==='undefined'?null:sessionStorage.getItem(SESSION_KEY);
 if(id){try{return {session_id:id,memory:await api<Memory>(`/sessions/${id}/memory`)}}catch(error){if(!('status' in (error as object))||(error as {status:number}).status!==404)throw error;sessionStorage.removeItem(SESSION_KEY);sessionStorage.removeItem('hiresense-results')}}
 const session=await api<SessionInfo>('/sessions',{method:'POST'});sessionStorage.setItem(SESSION_KEY,session.session_id);return session;
}
