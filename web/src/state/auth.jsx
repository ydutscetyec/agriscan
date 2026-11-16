import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, getToken, onUnauthorized, setToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  // Set when the server ended the session (expired, password changed elsewhere,
  // account deactivated), so the sign-in page can say why the person is there.
  const [endedReason, setEndedReason] = useState(null)
  // Counts sign-ins made through the form in this tab. A restored session after a
  // page reload does not increment it, which is how the tour tells "someone just
  // arrived" from "someone pressed F5 halfway through their work".
  const [signInCount, setSignInCount] = useState(0)
  const userRef = useRef(null)
  useEffect(() => { userRef.current = user }, [user])

  useEffect(() => {
    if (!getToken()) {
      setChecking(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false))
  }, [])

  useEffect(
    () =>
      onUnauthorized(() => {
        if (userRef.current) setEndedReason('Your session ended. Sign in again to continue.')
        setUser(null)
      }),
    [],
  )

  const value = useMemo(
    () => ({
      user,
      checking,
      endedReason,
      signInCount,
      async signIn(name, password) {
        const result = await api.login(name, password)
        setToken(result.token)
        setUser(result.user)
        setEndedReason(null)
        setSignInCount((n) => n + 1)
        return result.user
      },
      /** After a password change the server issues a fresh token for this device. */
      replaceSession(token, nextUser) {
        setToken(token)
        setUser(nextUser)
      },
      signOut() {
        setToken(null)
        setUser(null)
        setEndedReason(null)
      },
      can(...roles) {
        return !!user && roles.includes(user.role)
      },
    }),
    [user, checking, endedReason, signInCount],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
