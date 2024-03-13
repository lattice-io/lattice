export default [
  {
    path: '/',
    component: './layouts/RootLayout',
    routes: [
      {
        path: '/',
        routes: [
          {
            path: '/',
            component: './layouts/BasicLayout',
            routes: [
              {
                path: '/',
                icon: 'MonitorOutlined',
                name: 'Jobs',
                component: './pages/Monitor',
              },
              // {
              //   path: '/team',
              //   icon: 'TeamOutlined',
              //   name: 'Team Members',
              //   component: './pages/Team',
              // },
              // {
              //   path: '/settings',
              //   icon: 'SettingOutlined',
              //   name: 'Settings',
              //   component: './pages/Settings',
              // },
            ],
          },
          {
            component: './pages/404',
          },
        ],
      },
      {
        component: './pages/404',
      },
    ],
  },
  {
    component: './pages/404',
  },
]
