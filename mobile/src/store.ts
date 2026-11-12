import * as SecureStore from 'expo-secure-store';
import * as SQLite from 'expo-sqlite';
export const STORE_OPTIONS={keychainAccessible:SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY};
export type Session={origin:string;token:string;user:{id:number;username:string;full_name:string;role:string;salesperson_id:number|null}};
export type Shift={session_id:string;device_id:string;started_at:string;expires_at:string;collecting:boolean};
export async function session():Promise<Session|null>{const x=await SecureStore.getItemAsync('session');return x?JSON.parse(x):null;}
export async function shift():Promise<Shift|null>{const x=await SecureStore.getItemAsync('shift');return x?JSON.parse(x):null;}
export async function saveSession(s:Session|null){if(s)await SecureStore.setItemAsync('session',JSON.stringify(s),STORE_OPTIONS);else await SecureStore.deleteItemAsync('session');}
export async function saveShift(s:Shift|null){if(s)await SecureStore.setItemAsync('shift',JSON.stringify(s),STORE_OPTIONS);else await SecureStore.deleteItemAsync('shift');}
let pending:Promise<SQLite.SQLiteDatabase>|undefined;
export function db(){if(!pending)pending=(async()=>{const d=await SQLite.openDatabaseAsync('kiarad-location.db');await d.execAsync('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,payload TEXT NOT NULL); CREATE INDEX IF NOT EXISTS queue_session ON queue(session_id);');return d;})();return pending;}
export async function count(){return (await (await db()).getFirstAsync<{n:number}>('SELECT COUNT(*) AS n FROM queue'))?.n||0;}
export async function request<T>(path:string,body?:unknown,method?:string):Promise<T>{const s=await session();if(!s)throw new Error('ابتدا وارد حساب شوید.');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);try{const response=await fetch(s.origin+'/api'+path,{method:method||(body===undefined?'GET':'POST'),headers:{Authorization:'Bearer '+s.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});if(!response.ok){const r=await response.json().catch(()=>null);throw new Error(typeof r?.detail==='string'?r.detail:`خطای سرور ${response.status}؛ داده در صف محفوظ است.`);}return await response.json();}finally{clearTimeout(timer);}}
