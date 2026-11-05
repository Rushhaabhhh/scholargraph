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
 await page.getByLabel('WHAT ARE YOU WORKING ON?').fill('graph retrieval');await page.getByRole('button',{name:/Find experts/}).click();
 const card=page.locator('article').first();await expect(card).toBeVisible({timeout:60000});
 await card.getByRole('button',{name:'+ Shortlist'}).click();await expect(card.getByRole('button',{name:'✓ Shortlisted'})).toBeVisible();
 await page.getByText('Session memory').click();await page.getByRole('button',{name:'Clear all memory'}).click();
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
