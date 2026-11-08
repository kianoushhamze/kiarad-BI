/** Keeps an uncertain request in this page's memory; never stores it offline. */
export class PendingSubmission<T> {
  private pending: {signature:string;key:string;payload:T}|null=null;
  constructor(private readonly makeKey=()=>crypto.randomUUID()) {}
  get(signature:string) {return this.pending?.signature===signature?this.pending:null;}
  prepare(signature:string,payload:T) {
    const previous=this.get(signature);
    if(previous)return previous;
    this.pending={signature,key:this.makeKey(),payload:JSON.parse(JSON.stringify(payload)) as T};
    return this.pending;
  }
  clear(key:string) {if(this.pending?.key===key)this.pending=null;}
}
