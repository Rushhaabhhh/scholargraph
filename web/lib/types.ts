export type Person = {person_id:number; name:string};
export type Evidence = {paper_id:string; title:string; year:number|null; source:string; collaborators:Person[]};
export type Claim = {text:string; supported:boolean; reason:string|null; paper_id:string; data_warnings:string[]};
export type Expert = Person & {score:number; explanation:string; evidence:Evidence[]; claims:Claim[]; grounding:{claims:number; unsupported:number}; shortlisted:boolean};
export type Memory = {version:number; shortlisted_person_ids:number[]; rejected_person_ids:number[]; last_query:string|null; last_result_ids:number[]};
export type SearchResponse = {query:string; results:Expert[]; memory:Memory|null; understanding:{provider:string; used_fallback:boolean}; effective_filters:{graph_cutoff_year:number; since_year:number|null}};
export type Profile = Person & {publications:{paper_id:string; title:string; year:number|null; venue:string|null; source:string}[]; topics:{topic:string; source_paper_ids:string[]; supported:boolean}[]; name_sources:string[]};
export type ChatResponse = {message:string; results:Expert[]; memory:Memory; memory_applied:Memory; tool_calls:{tool:string; outcome:string; arguments:Record<string,unknown>}[]; claims:Claim[]; profile:Profile|null; profiles:Profile[]|null; path:{person_ids:number[]; edges:{from:number; to:number; evidence:{paper_id:string; title:string; year:number|null}[]}[]; truncated:boolean}|null; safety:{blocked:boolean}};
