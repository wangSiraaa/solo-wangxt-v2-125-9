import { chromium } from 'playwright'

// 预测练习端到端：出题 → 提交预测 → 揭示两次实算 → 历史复看 → 静风变体
const errors: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('console', (m) => {
  if (m.type() === 'error') errors.push('console: ' + m.text())
})
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

// 1. 打开预测练习页签
await page.getByRole('button', { name: '预测练习' }).click()
await page.waitForTimeout(400)
const submitBtn = page.locator('[data-test="prediction-submit"]')
console.log('submit disabled before prediction:', await submitBtn.isDisabled())

// 2. 排放率 50 -> 100 g/s，预测“升高”
await page.locator('.panel.right select.num').first().selectOption('emission_rate_g_s')
await page.locator('.panel.right input[type="number"]').nth(2).fill('100')
await page.getByRole('radio', { name: '升高' }).check()
// 提交前：结果区不应存在
const beforeTables = await page.locator('.panel.right table.meta-tbl').count()
await submitBtn.click()
await page.waitForTimeout(1200)
const verdict = await page.locator('.panel.right .section h2 .badge').first().textContent()
console.log('emission doubling verdict badge:', verdict?.trim())
const deltaCell = await page.locator('.panel.right table.meta-tbl tr').nth(3).locator('td').nth(3).textContent()
console.log('delta total cell:', deltaCell?.trim(), '| tables before submit:', beforeTables)

// 3. 再出一题：静风变体（风速 -> 0.3），预测“降低”
await page.getByRole('button', { name: '再出一题' }).click()
await page.locator('.panel.right select.num').first().selectOption('wind_speed_ms')
await page.locator('.panel.right input[type="number"]').nth(2).fill('0.3')
await page.getByRole('radio', { name: '降低' }).check()
await submitBtn.click()
await page.waitForTimeout(1200)
const calmBadge = await page.locator('.panel.right .section h2 .badge').first().textContent()
const calmNotice = await page.locator('.panel.right .notice.warn').first().textContent()
console.log('calm variant badge:', calmBadge?.trim())
console.log('calm notice mentions 静风:', calmNotice?.includes('静风'))

// 4. 历史题次：应有两条，可展开复看
const histCount = await page.locator('.panel.right .check-item').count()
await page.locator('.panel.right .check-item .t').first().click()
await page.waitForTimeout(300)
console.log('history items:', histCount)

await page.screenshot({ path: '/tmp/plume-predict.png' })

const pass =
  verdict?.includes('预测正确') &&
  calmBadge?.includes('不可计算') &&
  histCount >= 2 &&
  beforeTables === 0
if (errors.length || !pass) {
  console.log('JS ERRORS:', errors, 'PASS:', pass)
  process.exit(1)
}
console.log('prediction exercise e2e passed, no JS errors')
await browser.close()
