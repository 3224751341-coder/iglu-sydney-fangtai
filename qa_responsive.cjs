// Local, isolated browser. Only the generated page is served; external requests are blocked.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');

(async () => {
  const output = path.join(__dirname, 'qa-output');
  fs.mkdirSync(output, {recursive:true});
  const runtime = fs.mkdtempSync(path.join(output,'runtime-'));
  fs.mkdirSync(path.join(runtime,'public'));
  fs.copyFileSync(path.join(__dirname,'container/server.mjs'),path.join(runtime,'server.mjs'));
  fs.copyFileSync(process.env.IGLU_QA_PAGE || path.join(__dirname,'container/public/index.html'),path.join(runtime,'public/index.html'));
  const reserve = http.createServer();
  await new Promise(resolve => reserve.listen(0,'127.0.0.1',resolve));
  const port = reserve.address().port;
  await new Promise(resolve => reserve.close(resolve));
  const server = spawn(process.execPath,[path.join(runtime,'server.mjs')],{env:{...process.env,PORT:String(port)},stdio:['ignore','pipe','pipe']});
  let browser;
  try {
    await new Promise((resolve,reject) => {
      const timer=setTimeout(()=>reject(new Error('Local server did not start')),10000);
      server.stdout.on('data',data=>{if(data.toString().includes('listening on')){clearTimeout(timer);resolve();}});
      server.once('error',error=>{clearTimeout(timer);reject(error);});
      server.once('exit',code=>{clearTimeout(timer);reject(new Error('Server exited '+code));});
    });
    browser = await chromium.launch({headless:true});
    const origin = `http://127.0.0.1:${port}`;
    const results = [];
    for (const width of [320,390,500,1440]) {
      const context = await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:1});
      await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.fulfill({status:200,body:''}));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
      await page.goto(origin);
      const chip = page.locator('body > div').filter({hasText:'最新更新'}).last();
      assert.equal(await chip.count(),1);
      assert.ok(await chip.evaluate(el=>!['fixed','sticky','absolute'].includes(getComputedStyle(el).position)), 'Sync chip must remain in document flow');
      assert.ok(await chip.evaluate(el=>el.getBoundingClientRect().top>innerHeight),'Sync chip must not cover initial navigation');
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.addStyleTag({content:'.fade-in{animation:none!important;opacity:1!important;transform:none!important}'});
      const targets = await page.locator('.city-block .prop-btn').evaluateAll(buttons => buttons.map(b => ({city:b.closest('.city-block').dataset.city,slug:b.id.replace('prop-btn-','')})));
      for (const target of targets) {
        await page.evaluate(({city,slug}) => {switchCity(city);switchProp(city,slug);document.querySelectorAll('.prop-panel.active .u18-block, .prop-panel.active .room-overview details').forEach(d => d.open = true);}, target);
        const overflow = await page.evaluate(() => ({doc:document.documentElement.scrollWidth,viewport:innerWidth,
          bad:[...document.querySelectorAll('body *')].filter(el => {const r=el.getBoundingClientRect();return r.width && (r.right>innerWidth+1 || r.left < -1);}).slice(0,6).map(el=>el.className)}));
        assert.ok(overflow.doc <= width, JSON.stringify({width,target,overflow}));
        await page.locator('.city-block.active .prop-panel.active').screenshot({path:path.join(output,`${width}-${target.city}-${target.slug}.png`)});
      }
      await page.evaluate(() => {switchCity('sydney');switchProp('sydney','broadway');});
      const premium = page.locator('#prop-broadway tr:not(.room-overview)').filter({hasText:'Premium Studio'});
      assert.equal(await premium.count(),2);
      assert.match(await premium.allTextContents().then(x=>x.join(' ')),/S2 2026.*等位/);
      assert.doesNotMatch(await premium.allTextContents().then(x=>x.join(' ')),/仅剩2间|今年无房/);
      const overview = page.locator('#prop-broadway .room-overview').filter({hasText:'Premium Studio'});
      if (await overview.count()) await overview.screenshot({path:path.join(output,`${width}-overview.png`)});
      await premium.last().evaluate(el => window.scrollTo(0, el.getBoundingClientRect().top + scrollY - 100));
      await page.screenshot({path:path.join(output,`${width}-premium-viewport.png`)});
      await page.locator('#cmpTermSeg [data-term="lowest"]').click();
      let quote = page.locator('.cmp-row').filter({hasText:'Broadway'}).filter({hasText:'Premium Studio'}).filter({hasText:'Semester 1 2027'});
      assert.match(await quote.innerText(),/\$850/);
      assert.match(await quote.innerText(),/短租/);
      assert.doesNotMatch(await quote.innerText(),/仅剩2间|2间/);
      await quote.locator('summary').click();
      assert.match(await quote.innerText(),/租期日期未核验/);
      await page.locator('#cmpTermSeg [data-term="44周"]').click();
      quote = page.locator('.cmp-row').filter({hasText:'Broadway'}).filter({hasText:'Premium Studio'}).filter({hasText:'Semester 1 2027'});
      assert.match(await quote.innerText(),/\$1,035/);
      assert.match(await quote.innerText(),/44周/);
      await page.locator('#cmpCard').screenshot({path:path.join(output,`${width}-compare.png`)});
      await quote.evaluate(el => window.scrollTo(0, el.getBoundingClientRect().top + scrollY - 100));
      await page.screenshot({path:path.join(output,`${width}-compare-viewport.png`)});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      await chip.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output,`${width}-sync-chip.png`)});
      assert.deepEqual(errors,[]);
      if(width < 760) assert.ok(await page.locator('#cmpSearch').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=16));
      results.push({width,properties:targets.length,errors:0});
      await context.close();
    }
    console.log(JSON.stringify(results));
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit',resolve));
    fs.rmSync(runtime,{recursive:true});
  }
})().catch(error => {console.error(error);process.exitCode=1;});
