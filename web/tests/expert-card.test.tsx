import React from 'react';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ExpertCard} from '../components/ExpertCard';
import type {Expert} from '../lib/types';
afterEach(cleanup);
const expert:Expert={person_id:1,name:'Ada Example',score:.42,explanation:'Evidence-based match',shortlisted:false,grounding:{claims:1,unsupported:1},claims:[{kind:'authorship',person_id:1,paper_id:'p1',year:2020,collaborator_id:null,term:null,text:'Unverified claim',supported:false,reason:'Not in graph',sources:[],data_warnings:[]}],evidence:[{paper_id:'p1',title:'<script>window.poisoned=true</script>',year:2020,source:'dblp',collaborators:[]}]};
describe('expert evidence and decisions',()=>{
 it('renders untrusted source text as text and marks unsupported claims',()=>{render(<ExpertCard expert={expert} index={0} memory={null} busy={false} onDecision={()=>{}} onAsk={()=>{}}/>);fireEvent.click(screen.getByText(/View evidence/));expect(screen.getByText(expert.evidence[0].title)).toBeTruthy();expect(document.querySelector('script')).toBeNull();expect(screen.getByText(/Some claims could not be verified/)).toBeTruthy();expect(screen.getByText(/Unverified: Unverified claim/)).toBeTruthy()});
 it('emits a decision without pretending it was saved',()=>{const decide=vi.fn();render(<ExpertCard expert={expert} index={0} memory={null} busy={false} onDecision={decide} onAsk={()=>{}}/>);fireEvent.click(screen.getByRole('button',{name:'+ Shortlist'}));expect(decide).toHaveBeenCalledWith(1,'shortlist');expect(screen.getByRole('button',{name:'+ Shortlist'})).toBeTruthy()});
});
