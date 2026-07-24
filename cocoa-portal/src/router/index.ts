import { createRouter, createWebHistory, type Router } from 'vue-router'

// Cocoa Portal — routes are added in P8. Empty array is intentional for the P0 scaffold.
const routes: Router['options']['routes'] = []

export const router: Router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
