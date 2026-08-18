/**
 * Local Block N credentials. Must stay in sync with
 * backend/scripts/seed_tenants.py.
 *
 * Shown on /login in development only.
 */
export const DEV_ADMIN_LOGIN = {
  title: "Account 1: Full Admin",
  tenant: "alpha",
  email: "admin@synq.dev",
  password: "AlphaAdmin123!",
  role: "admin",
} as const

export const DEV_MEMBER_LOGIN = {
  title: "Account 2: Standard Member (Search & Read Only)",
  tenant: "alpha",
  email: "member@alpha.test",
  password: "AlphaMember123!",
  role: "member",
} as const
