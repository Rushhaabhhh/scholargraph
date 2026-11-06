import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {EvidenceGraph} from '../components/EvidenceGraph';
import type {Expert} from '../lib/types';

afterEach(cleanup);
const expert:Expert={person_id:1,name:'Ada Example',score:.5,explanation:'Match',shortlisted:false,grounding:{claims:0,unsupported:0},claims:[],evidence:[{paper_id:'conf/example',title:'A shared publication',year:2018,source:'dblp',collaborators:[{person_id:2,name:'Sam Coauthor'}]}]};
it('highlights returned authorship connections and shows paper details on hover or focus',()=>{
 const {container}=render(<EvidenceGraph experts={[expert]}/>);
 expect(container.querySelectorAll('.network-node')).toHaveLength(3);
 expect(container.querySelectorAll('.network-edge')).toHaveLength(2);
 const publication=screen.getByRole('button',{name:'Publication: A shared publication'});
 fireEvent.pointerEnter(publication);
 expect(screen.getByText('THE PUBLICATION · 2018 · DBLP')).toBeTruthy();
 expect(screen.getByText('DBLP RECORD · conf/example')).toBeTruthy();
 expect(container.querySelectorAll('.network-edge.is-highlighted')).toHaveLength(2);
 expect(container.querySelectorAll('.network-node.is-connected')).toHaveLength(2);
 fireEvent.pointerLeave(publication);
 expect(screen.getByText('Follow the work. Find the people.')).toBeTruthy();
 fireEvent.focus(publication);
 expect(screen.getByText('THE PUBLICATION · 2018 · DBLP')).toBeTruthy();
});
it('includes five matches and up to two returned papers each, with keyboard navigation',()=>{
 const experts=Array.from({length:11},(_,i)=>({...expert,person_id:i+10,name:`Researcher ${i}`,evidence:Array.from({length:4},(_,j)=>({...expert.evidence[0],paper_id:`p${i}-${j}`,title:`Paper ${i}-${j}`,collaborators:[]}))}));
 const {container}=render(<EvidenceGraph experts={experts}/>);
 expect(container.querySelectorAll('.node-match')).toHaveLength(5);
 expect(container.querySelectorAll('.node-paper')).toHaveLength(10);
 expect(container.querySelectorAll('.network-node text')).toHaveLength(15);
 const graph=screen.getByRole('group',{name:/Research evidence network/});
 fireEvent.keyDown(graph,{key:'+'});
 expect(container.querySelector('.network-graph > g')?.getAttribute('transform')).toContain('scale(1.25)');
 fireEvent.keyDown(graph,{key:'ArrowRight'});
 expect(container.querySelector('.network-graph > g')?.getAttribute('transform')).toContain('rotate(15)');
 fireEvent.keyDown(graph,{key:'0'});
 expect(container.querySelector('.network-graph > g')?.getAttribute('transform')).toContain('scale(1)');
});
