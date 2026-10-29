import { expect, test, type Page } from '@playwright/test'

const answers: Record<string, string> = {
  'Name a planet in our Solar System.': 'Earth',
  "Name one of Earth's five oceans.": 'Pacific',
  'Name one of the five Great Lakes of North America.': 'Michigan',
  'Name a permanent member of the UN Security Council.': 'United States',
  'Name a country that shares a land border with Germany.': 'France',
  'Name a noble gas on the periodic table.': 'Helium',
  'Name a Shakespeare play classified as a tragedy in the First Folio.': 'Hamlet',
  'Name a feature film directed by Christopher Nolan through 2023.': 'Inception',
  'Name a core Beatles studio album released in the UK.': 'Abbey Road',
  'Name a person who has walked on the Moon.': 'Neil Armstrong',
  'Name a Canadian province (not a territory).': 'Ontario',
  'Name a US state whose name begins with M.': 'Michigan',
  'Name one of the Seven Wonders of the Ancient World.': 'Great Pyramid',
  'Name an original suspect in the board game Clue (Cluedo).': 'Miss Scarlet',
  'Name a tetromino shape used in Tetris.': 'T piece',
  'Name one of the seven colors traditionally listed in a rainbow.': 'Red',
  'Name a sliding sport currently contested at the Winter Olympics.': 'Bobsled',
  "Name one of tennis's four Grand Slam tournaments.": 'Wimbledon',
  'Name one of the four Teenage Mutant Ninja Turtles.': 'Leonardo',
  'Name one of the four original Ghostbusters in the 1984 film.': 'Peter Venkman',
}

async function join(page: Page, code: string, nickname: string) {
  await page.goto(`/room/${code}`)
  await page.getByLabel('What should we call you?').fill(nickname)
  await page.getByRole('button', { name: 'Join the game' }).click()
  await expect(page.getByText(`You're in, ${nickname}.`)).toBeVisible()
}

async function answerCurrentQuestion(page: Page) {
  const heading = await page.locator('h1').innerText()
  const answer = answers[heading]
  expect(answer, `No fixture answer for: ${heading}`).toBeTruthy()
  await page.getByLabel('Your answer').fill(answer)
  await page.getByRole('button', { name: 'Submit answer' }).click()
  await expect(page.getByText('Answer locked in')).toBeVisible()
}

test('three phones complete seven rounds, reveal together, and rematch', async ({ browser }) => {
  const hostContext = await browser.newContext()
  const playerTwoContext = await browser.newContext()
  const playerThreeContext = await browser.newContext()
  const host = await hostContext.newPage()
  const playerTwo = await playerTwoContext.newPage()
  const playerThree = await playerThreeContext.newPage()

  await host.goto('/')
  await host.getByRole('button', { name: 'Create game' }).click()
  await host.getByPlaceholder('Your nickname').fill('Avery')
  await host.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(host.getByText("You're in, Avery.")).toBeVisible()
  const roomCode = (await host.locator('button').filter({ hasText: /^[A-Z2-9]{6}/ }).innerText())
    .trim()
    .slice(0, 6)

  await Promise.all([join(playerTwo, roomCode, 'Blair'), join(playerThree, roomCode, 'Casey')])
  await expect(host.getByText('Blair')).toBeVisible()
  await expect(host.getByText('Casey')).toBeVisible()
  await host.getByRole('button', { name: 'Start game' }).click()

  for (let round = 1; round <= 7; round += 1) {
    await expect(host.getByText(`Question ${round} of 7`, { exact: false })).toBeVisible()
    await host.getByRole('button', { name: /Start 25-second timer/ }).click()
    await Promise.all([
      answerCurrentQuestion(host),
      answerCurrentQuestion(playerTwo),
      answerCurrentQuestion(playerThree),
    ])
    await expect(host.getByRole('heading', { name: 'The reveal' })).toBeVisible({ timeout: 32_000 })
    for (const page of [host, playerTwo, playerThree]) {
      await expect(page.getByText('Avery', { exact: false })).toBeVisible()
      await expect(page.getByText('Blair', { exact: false })).toBeVisible()
      await expect(page.getByText('Casey', { exact: false })).toBeVisible()
    }
    await host.getByRole('button', { name: 'Show leaderboard' }).click()
    await expect(playerTwo.getByRole('heading', { name: `After ${round} questions` })).toBeVisible()
    await host.getByRole('button', { name: round === 7 ? 'See final results' : 'Next question' }).click()
  }

  await expect(playerThree.getByText('Game over')).toBeVisible()
  await host.getByRole('button', { name: 'Play a rematch' }).click()
  await expect(playerTwo.getByText('Question 1 of 7', { exact: false })).toBeVisible()

  await Promise.all([hostContext.close(), playerTwoContext.close(), playerThreeContext.close()])
})

