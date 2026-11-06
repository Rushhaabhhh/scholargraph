import {test,expect} from '@playwright/test';

test('repeated disconnects and interruptions do not lock the model for later conversations',async({page,context})=>{
 test.setTimeout(180000);
 let current=page;
 for(let cycle=0;cycle<2;cycle++){
  await current.goto('/chat');
  if(cycle)await current.getByRole('button',{name:'+ New'}).click();
  const input=current.getByLabel('Message',{exact:true});
  await input.fill('Explain computer science in detail, with several examples.');
  await current.getByRole('button',{name:/^Send/}).click();
  await expect(current.locator('.conversation-message.assistant').last()).not.toHaveText(/Generating/,{timeout:60000});
  await current.close();
  current=await context.newPage();
 }
 await current.goto('/chat');
 await current.getByRole('button',{name:'+ New'}).click();
 const input=current.getByLabel('Message',{exact:true});await input.fill('Say hello briefly.');
 await current.getByRole('button',{name:/^Send/}).click();
 await expect(current.getByRole('button',{name:/^Send/})).toBeVisible({timeout:60000});
 await expect(current.locator('.conversation-message.assistant').last()).not.toContainText('No response generated.');
 await expect(current.locator('.conversation-error[role="alert"]')).toHaveCount(0);
});
