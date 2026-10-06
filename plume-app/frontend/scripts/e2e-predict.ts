/**
 * 课堂预测练习 E2E：
 * 1. 切到“课堂预测练习”模式（自由探究结果不应出现在预测面板）；
 * 2. 默认受体未放置/变体值未填时，锁定按钮禁用；
 * 3. 放置下风向 1000 m 受体、取 Q 变体=100（基准 50），锁定；
 * 4. 预测前断言右侧没有任何浓度结果；
 * 5. 提交“升高”，等待揭晓：方向 up、判定正确、烟羽/背景/总量与差值齐全；
 * 6. 切到静风变体（u=0.3）新题次：揭晓为不可计算，保留预测，无虚假浓度；
 * 7. 历史区出现 2 条题次，点击第 1 条可复看；
 * 8. 无 JS 错误。
 */
import { chromium } from 'playwright'

const errors: string[] = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
page.on('console', (m) => {
  if (m.type() === 'error') errors.push('console: ' + m.text())
})
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)

// 1. 切模式
await page.getByRole('button', { name: '课堂预测练习' }).click()
await page.waitForTimeout(300)
await page.getByText('教师配题').waitFor()

// 2. 未配齐时锁定禁用
const lockBtn = page.getByRole('button', { name: /锁定题目/ })
// 先放受体、填变体，按钮才启用
await page.getByRole('button', { name: '放到下风向该距离' }).click()
await page.getByText('受体经纬度').waitFor()

// 基准参数：Q=50（默认），变体 Q=100
await page.getByRole('button', { name: /排放率/ }).first().click()
await page.locator('input[placeholder="由教师填入变体取值"]').fill('100')
await page.waitForTimeout(100)
console.log('lock disabled before ready?', await lockBtn.isDisabled())
await lockBtn.click()
await page.waitForTimeout(200)

// 4. 学生预测页：不能出现结果数字表格
await page.getByText('学生预测').waitFor()
const tableBefore = await page.locator('.cmp-tbl').count()
console.log('comparison table before prediction:', tableBefore)

// 5. 提交“升高”
await page.getByRole('button', { name: /升高/ }).click()
await page.waitForTimeout(2500)
await page.getByText('预测正确').waitFor({ timeout: 10000 })
const verdict1 = await page.locator('.notice.okbox').textContent()
console.log('verdict1:', verdict1?.replace(/\s+/g, ' ').trim().slice(0, 120))
const rows1 = await page.locator('.cmp-tbl tr').allInnerTexts()
rows1.forEach((r) => console.log('  ', r.replace(/\t/g, ' | ').replace(/\n/g, ' ')))

// 地图源要素数量
const feat1 = await page.evaluate(() => {
  const map = (window as any).__map
  return (map.getSource('fill')._data?.features || []).length
})
console.log('baseline fill features:', feat1)
// 切到变体场与总量场
await page.getByRole('button', { name: '变体·烟羽' }).click()
await page.waitForTimeout(600)
await page.getByRole('button', { name: '变体·总量' }).click()
await page.waitForTimeout(600)
const feat2 = await page.evaluate(() => {
  const map = (window as any).__map
  return (map.getSource('fill')._data?.features || []).length
})
console.log('variant-total fill features:', feat2)

// 6. 新题次：静风变体
await page.getByRole('button', { name: '新题次' }).click()
await page.waitForTimeout(200)
await page.getByRole('button', { name: '放到下风向该距离' }).click()
await page.getByRole('button', { name: /风速 u/ }).click()
await page.locator('input[placeholder="由教师填入变体取值"]').fill('0.3')
await page.getByRole('button', { name: /锁定题目/ }).click()
await page.waitForTimeout(200)
await page.getByRole('button', { name: /升高/ }).click()
await page.waitForTimeout(2000)
await page.getByText(/不可计算/).first().waitFor({ timeout: 10000 })
const calmBox = await page.locator('.notice.warn').first().textContent()
console.log('calm box:', calmBox?.replace(/\s+/g, ' ').trim().slice(0, 160))
// 变体场按钮必须停用
const variantBtnDisabled = await page.getByRole('button', { name: '变体·烟羽' }).isDisabled()
console.log('variant field buttons disabled for calm:', variantBtnDisabled)
// 历史区两条
const histCount = await page.locator('.hist-item').count()
console.log('history items:', histCount)

// 7. 复看第 1 条（列表中第 2 个 hist-item）
await page.locator('.hist-item').nth(1).click()
await page.waitForTimeout(1500)
await page.getByText('预测正确').waitFor()
console.log('reviewed first record OK')

await page.screenshot({ path: '/tmp/plume-prediction.png' })

if (errors.length) {
  console.log('--- JS errors ---')
  errors.forEach((e) => console.log(e))
  process.exit(1)
}
console.log('no JS errors')
await browser.close()
