import {useEffect,useRef,useState} from 'react';
import {Alert,SafeAreaView,Text,TouchableOpacity,View,ActivityIndicator,StyleSheet} from 'react-native';
import {WebView,type WebViewMessageEvent} from 'react-native-webview';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as Crypto from 'expo-crypto';
import {session as readSession,saveSession,type Session} from './store';
import {sameOrigin,navigationAllowed,bootstrap,exportName,BRIDGE} from './panel-policy.cjs';
export function Panel({auth,onClose,onRenew,onSessionUpdated}:{auth:Session;onClose:()=>void;onRenew:()=>void;onSessionUpdated:()=>void}){
 const view=useRef<WebView<unknown>>(null),entryUsed=useRef(false),active=useRef(true),lastExport=useRef(0),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{active.current=true;return()=>{active.current=false;};},[]);
 async function updateSession(token:string){
  if(token.length>12000||token.length<20)return;const before=await readSession();if(!before||before.origin!==auth.origin||before.user.id!==auth.user.id)return;
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),20000);
  try{const r=await fetch(auth.origin+'/api/auth/me',{headers:{Authorization:'Bearer '+token},signal:abort.signal});if(!r.ok)return;const u=await r.json();const now=await readSession();if(!active.current||!now||now.token!==before.token||u.id!==auth.user.id||now.origin!==auth.origin)return;await saveSession({origin:auth.origin,token,user:{id:u.id,username:u.username,full_name:u.full_name,role:u.role,salesperson_id:u.salesperson_id}});onSessionUpdated();}finally{clearTimeout(timer);}
 }
 async function share(base64:string,name:string,mime:string){
  try{if(!await Sharing.isAvailableAsync())throw new Error('اشتراک‌گذاری فایل روی این دستگاه در دسترس نیست.');const uri=FileSystem.cacheDirectory+'kiarad-'+Crypto.randomUUID()+'-'+name;await FileSystem.writeAsStringAsync(uri,base64,{encoding:FileSystem.EncodingType.Base64});try{await Sharing.shareAsync(uri,{mimeType:mime,dialogTitle:'ذخیره یا اشتراک‌گذاری فایل کیاراد'});}finally{await FileSystem.deleteAsync(uri,{idempotent:true});}}catch(e){if(active.current)setError(e instanceof Error?e.message:'خروجی فایل ذخیره نشد.');}
 }
 async function message(event:WebViewMessageEvent){
  if(!sameOrigin(event.nativeEvent.url,auth.origin)||event.nativeEvent.data.length>15000000)return;
  try{const m=JSON.parse(event.nativeEvent.data);if(m.type==='session_updated'&&typeof m.token==='string'){await updateSession(m.token);return;}
   if(m.type==='export_error'){setError(typeof m.message==='string'?m.message.slice(0,300):'خروجی دریافت نشد.');return;}
   if(m.type!=='export'||typeof m.base64!=='string'||!/^[A-Za-z0-9+/]*={0,2}$/.test(m.base64)||m.base64.length>13981016||m.base64.length%4!==0)return;
   const name=exportName(m.name),size=Math.floor(m.base64.length*3/4)-(m.base64.endsWith('==')?2:m.base64.endsWith('=')?1:0);if(!size||size>10485760||Date.now()-lastExport.current<3000)return;lastExport.current=Date.now();
   const mime=typeof m.mime==='string'&&m.mime.length<150?m.mime:'application/octet-stream';Alert.alert('خروجی پنل',`فایل «${name}» ممکن است اطلاعات شرکت داشته باشد. ذخیره یا اشتراک‌گذاری شود؟`,[{text:'انصراف',style:'cancel'},{text:'ادامه',onPress:()=>void share(m.base64,name,mime)}]);
  }catch{setError('پیام پنل یا خروجی معتبر نبود.');}
 }
 return <SafeAreaView style={styles.root}><View style={styles.header}><TouchableOpacity accessibilityRole="button" onPress={onClose}><Text style={styles.link}>بازگشت به اپ</Text></TouchableOpacity><Text style={styles.title}>{auth.user.full_name} · پنل کامل</Text></View>{loading&&<ActivityIndicator color="#a78bfa" style={{padding:8}}/>}{!!error&&<Text accessibilityRole="alert" style={styles.error}>{error}</Text>}<WebView<unknown> ref={view} source={{uri:auth.origin+'/mobile-entry'}} originWhitelist={[auth.origin]} incognito cacheEnabled={false} domStorageEnabled javaScriptEnabled geolocationEnabled mixedContentMode="never" allowFileAccess={false} allowUniversalAccessFromFileURLs={false} allowFileAccessFromFileURLs={false} thirdPartyCookiesEnabled={false} sharedCookiesEnabled={false} setSupportMultipleWindows={false} javaScriptCanOpenWindowsAutomatically={false} injectedJavaScript={BRIDGE} injectedJavaScriptForMainFrameOnly onMessage={e=>void message(e)} onShouldStartLoadWithRequest={r=>{if(!navigationAllowed(r.url,auth.origin)){setError('پیوند خارج از نشانی شرکت در این نما باز نمی‌شود.');return false;}return true;}} onNavigationStateChange={s=>{if(sameOrigin(s.url,auth.origin)&&new URL(s.url).pathname==='/login'){onRenew();}}} onLoadStart={()=>setLoading(true)} onLoadEnd={e=>{setLoading(false);if(sameOrigin(e.nativeEvent.url,auth.origin)&&new URL(e.nativeEvent.url).pathname==='/mobile-entry'&&!entryUsed.current){entryUsed.current=true;view.current?.injectJavaScript(bootstrap(auth));}}} onError={()=>{setLoading(false);setError('پنل دریافت نشد؛ اتصال و نشانی HTTPS شرکت را بررسی کنید.');}} style={{flex:1,backgroundColor:'#07101f'}}/></SafeAreaView>;
}
const styles=StyleSheet.create({root:{flex:1,backgroundColor:'#07101f'},header:{padding:14,flexDirection:'row',justifyContent:'space-between',gap:10,alignItems:'center'},link:{color:'#c4b5fd'},title:{color:'#fff',fontWeight:'700',flex:1,textAlign:'right'},error:{padding:12,color:'#fda4af',textAlign:'right'}});
