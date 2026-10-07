// Local, isolated browser. Only the generated page is served; external requests are blocked.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');

(async () => {
  const output = path.join(__dirname, 'qa-output');
  fs.mkdirSync(output, {recursive:true});
  const server = http.createServer((req,res) => {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(fs.readFileSync(path.join(__dirname,'index.html')));
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true});
    const origin = `http://127.0.0.1:${server.address().port}`;
    const results = [];
    for (const width of [320,390,1440]) {
      const context = await browser.newContext({viewport:{width,height:1000},deviceScaleFactor:1});
      await context.route('**/*', route => route.request().url().startsWith(origin) ? route.continue() : route.fulfill({status:200,body:''}));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
      await page.goto(origin);
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.addStyleTag({content:'.fade-in{animation:none!important;opacity:1!important;transform:none!important}'});
      const targets = await page.locator('.city-block .prop-btn').evaluateAll(buttons => buttons.map(b => ({city:b.closest('.city-block').dataset.city,slug:b.id.replace('prop-btn-','')})));
      for (const target of targets) {
        await page.evaluate(({city,slug}) => {switchCity(city);switchProp(city,slug);document.querySelectorAll('.prop-panel.active .u18-block').forEach(d => d.open = true);}, target);
        const overflow = await page.evaluate(() => ({doc:document.documentElement.scrollWidth,viewport:innerWidth,
          bad:[...document.querySelectorAll('body *')].filter(el => {const r=el.getBoundingClientRect();return r.width && (r.right>innerWidth+1 || r.left < -1);}).slice(0,6).map(el=>el.className)}));
        assert.ok(overflow.doc <= width, JSON.stringify({width,target,overflow}));
        await page.locator('.city-block.active .prop-panel.active').screenshot({path:path.join(output,`${width}-${target.city}-${target.slug}.png`)});
      }
      await page.evaluate(() => {switchCity('sydney');switchProp('sydney','broadway');});
      const premium = page.locator('#prop-broadway tr').filter({hasText:'Premium Studio'});
      assert.equal(await premium.count(),2);
      assert.match(await premium.allTextContents().then(x=>x.join(' ')),/S2 2026.*等位/);
      assert.doesNotMatch(await premium.allTextContents().then(x=>x.join(' ')),/仅剩2间|今年无房/);
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
      assert.deepEqual(errors,[]);
      if(width < 760) assert.ok(await page.locator('#cmpSearch').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=16));
      results.push({width,properties:targets.length,errors:0});
      await context.close();
    }
    console.log(JSON.stringify(results));
  } finally {
    if (browser) await browser.close();
    server.close();
  }
})().catch(error => {console.error(error);process.exitCode=1;});
