import {test,expect} from '@playwright/test';
test('search, inspect evidence, ask assistant and save a decision',async({page})=>{
 await page.goto('/');
 await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');
 await page.getByRole('button',{name:/Find experts/}).click();
 const card=page.locator('article').first();
 await expect(card).toBeVisible({timeout:60000});
 await card.getByText(/View evidence/).click();
 await expect(card.getByText(/DBLP ·/).first()).toBeVisible();
 await page.getByLabel('Message research assistant').fill('profile #1');
 await page.getByRole('button',{name:'Send message'}).click();
 await expect(page.getByText('Retrieved the sourced publication profile.')).toBeVisible();
 await page.getByText('Tools & memory applied').click();
 await expect(page.getByText(/get_profile \(success\)/)).toBeVisible();
 await card.getByRole('button',{name:'+ Shortlist'}).click();
 await expect(card.getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await page.getByText('Session memory').click();
 await expect(page.getByText(/1 saved/)).toBeVisible();
 await card.locator('a').first().click();
 await expect(page.getByRole('heading',{name:'Publication timeline'})).toBeVisible();
});
test('failed shortlist is not shown as saved',async({page})=>{
 await page.goto('/');await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const card=page.locator('article').first();await expect(card).toBeVisible({timeout:60000});
 await page.route('**/api/sessions/*/decisions/*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({code:'failure',message:'Decision could not be saved'})}));
 await card.getByRole('button',{name:'+ Shortlist'}).click();await expect(page.getByText('Decision could not be saved')).toBeVisible();await expect(card.getByRole('button',{name:'+ Shortlist'})).toBeVisible();
});
test('a newer search wins when an earlier search is delayed',async({page})=>{
 await page.goto('/');
 let searches=0;
 await page.route('**/api/search',async route=>{searches++;if(searches===1)await new Promise(resolve=>setTimeout(resolve,1400));try{await route.continue()}catch{}});
 await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');
 await page.getByRole('button',{name:/Find experts/}).click();
 await expect.poll(()=>searches).toBe(1);
 await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('information retrieval');
 await page.getByRole('button',{name:/Search again/}).click();
 await expect(page.locator('article').first()).toBeVisible({timeout:60000});
 await page.waitForTimeout(1600);
 await expect(page.getByLabel('WHAT ARE YOU WORKING ON?')).toHaveValue('information retrieval');
 await expect(page.getByRole('heading',{name:/Matched experts/})).toBeVisible();
});
test('mobile layout remains usable and memory can be cleared',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await page.getByRole('button',{name:'Open navigation'}).click();await expect(page.getByRole('dialog',{name:'Main navigation'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog',{name:'Main navigation'})).toHaveCount(0);
 await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const card=page.locator('article').first();await expect(card).toBeVisible({timeout:60000});
 await card.getByRole('button',{name:'+ Shortlist'}).click();await expect(card.getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await page.getByRole('button',{name:/Research assistant/}).click();await page.getByText('Session memory').click();page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Clear all memory'}).click();
 await expect(card.getByRole('button',{name:'+ Shortlist'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test('rejected results do not renumber assistant references',async({page})=>{
 await page.goto('/');await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const cards=page.locator('article');await expect(cards.nth(1)).toBeVisible({timeout:60000});
 const second=await cards.nth(1).locator('a').first().textContent();
 await cards.first().getByRole('button',{name:/Reject/}).click();
 await expect(cards.first().locator('.result-number')).toHaveText('02');
 await page.getByLabel('Message research assistant').fill('profile #2');await page.getByRole('button',{name:'Send message'}).click();
 await expect(page.getByRole('link',{name:`View ${second}’s profile →`})).toBeVisible();
});
test('supported recency and year filters are sent to search',async({page})=>{
 await page.goto('/');await page.getByLabel('Since year').fill('2018');await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');
 let sent:Record<string,unknown>|undefined;page.on('request',request=>{if(request.url().endsWith('/api/search'))sent=request.postDataJSON()});
 await page.getByRole('button',{name:/Find experts/}).click();await expect(page.locator('article').first()).toBeVisible({timeout:60000});
 expect(sent?.since_year).toBe(2018);expect(sent?.recency_preference).toBe('any');await expect(page.getByText('Since 2018 ×')).toBeVisible();
});
test('shortlist route compares and changes server-backed decisions',async({page})=>{
 await page.goto('/');await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const cards=page.locator('article');await expect(cards.nth(1)).toBeVisible({timeout:60000});
 await cards.nth(0).getByRole('button',{name:'+ Shortlist'}).click();await expect(cards.nth(0).getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await cards.nth(1).getByRole('button',{name:'+ Shortlist'}).click();await expect(cards.nth(1).getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await page.getByRole('link',{name:'My experts'}).click();await expect(page.getByRole('heading',{name:'My experts'})).toBeVisible();
 await expect(page.getByText('Shortlisted',{exact:false}).first()).toBeVisible();
 const checks=page.getByRole('checkbox');await checks.nth(0).check();await checks.nth(1).check();await page.getByRole('button',{name:'Compare selected experts'}).click();await expect(page.getByRole('heading',{name:'Compare experts'})).toBeVisible();
 await page.getByRole('button',{name:'Close'}).click();await page.locator('.saved-card').first().getByRole('button',{name:'Reject'}).click();await page.getByRole('tab',{name:/Rejected/}).click();await expect(page.locator('.saved-card')).toHaveCount(1);
 await page.locator('.saved-card').getByRole('button',{name:'Restore'}).click();await expect(page.getByRole('tab',{name:/Rejected/})).toContainText('0');
});
test('settings require confirmation and report server-confirmed session deletion',async({page})=>{
 await page.goto('/');await page.getByRole('link',{name:'Settings'}).click();await expect(page.getByRole('heading',{name:'Settings'})).toBeVisible();
 page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Delete session'}).click();await expect(page.getByText('Session decisions', {exact:false})).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Delete session'}).click();await expect(page.getByRole('status')).toContainText('Session memory deleted');
});
test('profile actions use the same server session and return to search',async({page})=>{
 await page.goto('/');await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const first=page.locator('article').first();await expect(first).toBeVisible({timeout:60000});const name=await first.locator('.person a').textContent();await first.locator('.person a').click();
 await expect(page.getByRole('heading',{name:'Publication timeline'})).toBeVisible();await expect(page.getByText(/Name source records/)).toBeVisible();
 await page.getByRole('button',{name:'+ Shortlist'}).click();await expect(page.getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await page.getByRole('link',{name:'Ask assistant about this expert'}).click();await expect(page).toHaveURL(/\/$/);await expect(page.getByLabel('Message research assistant')).toHaveValue(/Show profile/);
 await page.getByRole('button',{name:'Send message'}).click();await expect(page.getByText('Retrieved the sourced publication profile.')).toBeVisible();
 await expect(page.getByRole('heading',{name:/Matched experts/})).toBeVisible();expect(name).toBeTruthy();
});
