import {test,expect} from '@playwright/test';

test('independent conversation streams, restores and retains follow-up context',async({page,context})=>{
 test.setTimeout(120000);
 await page.goto('/chat');
 const input=page.getByLabel('Message',{exact:true});
 await input.fill('My name is Mira. Reply with a short greeting.');
 await page.getByRole('button',{name:/^Send/}).click();
 await expect(page.locator('.conversation-message.assistant').last()).not.toContainText('Generating…',{timeout:90000});
 await expect(page.getByRole('button',{name:/^Send/})).toBeVisible({timeout:90000});
 await input.fill('What is my name? Reply with just the name.');
 await page.getByRole('button',{name:/^Send/}).click();
 await expect(page.getByRole('button',{name:/^Send/})).toBeVisible({timeout:90000});
 await expect(page.locator('.conversation-message.assistant').last()).toContainText(/mira/i);
 await page.reload();
 await expect(page.locator('.conversation-message.user').getByText('My name is Mira. Reply with a short greeting.')).toBeVisible();
 await expect(page.locator('.conversation-message.user').getByText('What is my name? Reply with just the name.')).toBeVisible();
 await page.close();
 const reopened=await context.newPage();await reopened.goto('/chat');
 await expect(reopened.locator('.conversation-message.user').getByText('What is my name? Reply with just the name.')).toBeVisible();
});

test('research lookup operates inside a conversation',async({page})=>{
 test.setTimeout(120000);
 await page.goto('/chat');
 await page.getByLabel('Search research records for the next message').check();
 await page.getByLabel('Message',{exact:true}).fill('graph neural networks');
 const result=page.waitForResponse(r=>r.url().includes('/conversations/')&&r.url().endsWith('/messages')&&r.request().method()==='POST');
 await page.getByRole('button',{name:/^Send/}).click();
 expect((await result).ok()).toBeTruthy();
 await expect(page.getByRole('button',{name:/^Send/})).toBeVisible({timeout:90000});
 await expect(page.locator('.conversation-message.assistant').last()).not.toContainText('No response generated.');
 await page.reload();await expect(page.locator('.conversation-message.user').last()).toContainText('graph neural networks');
});

test('an explicit search command uses the research tool without enabling a checkbox',async({page})=>{
 test.setTimeout(90000);
 await page.goto('/chat');
 await page.getByLabel('Message',{exact:true}).fill('Search for graph neural networks');
 const response=page.waitForResponse(r=>r.url().includes('/conversations/')&&r.url().endsWith('/messages')&&r.request().method()==='POST');
 await page.getByRole('button',{name:/^Send/}).click();
 const stream=await response;expect(stream.ok()).toBe(true);
 const events=(await stream.text()).trim().split('\n').map(line=>JSON.parse(line));
 expect(events.some(event=>event.type==='tool'&&event.name==='research_records')).toBe(true);
 expect(events.some(event=>event.type==='delta'&&event.text)).toBe(true);
});

test('generation can be stopped and conversation remains usable',async({page})=>{
 test.setTimeout(120000);
 await page.goto('/chat');
 const input=page.getByLabel('Message',{exact:true});
 await input.fill('Write a long explanation of several areas of computer science, with examples.');
 await page.getByRole('button',{name:/^Send/}).click();
 await expect(page.getByRole('button',{name:'Stop',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Stop',exact:true}).click();
 await expect(input).toBeEnabled({timeout:20000});
 await input.fill('Say hello briefly.');
 await page.getByRole('button',{name:/^Send/}).click();
 await expect(page.getByRole('button',{name:/^Send/})).toBeVisible({timeout:90000});
 await expect(page.locator('.conversation-message.assistant').last()).not.toContainText('No response generated.');
});

test('a researcher can be discussed without changing search state',async({page})=>{
 test.setTimeout(120000);
 await page.goto('/');
 await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
 await page.getByRole('button',{name:/Find researchers/}).click();
 const card=page.locator('article').first();
 await expect(card).toBeVisible({timeout:60000});
 const name=await card.locator('.expert-identity a').textContent();
 await card.getByRole('button',{name:'Ask assistant'}).click();
 await expect(page).toHaveURL(/\/chat/);
 await expect(page.getByLabel('Message',{exact:true})).toHaveValue(`What can you tell me about ${name}'s research?`);
 await expect(page.getByText(`Profile: ${name}`)).toBeVisible();
});
