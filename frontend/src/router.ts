import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "home",
    component: () => import("./views/ServerList.vue"),
  },
  {
    path: "/server/:serverId",
    name: "server",
    component: () => import("./views/ServerDetail.vue"),
    props: true,
  },
  {
    path: "/server/:serverId/interview/:interviewId",
    name: "interview",
    component: () => import("./views/InterviewDetail.vue"),
    props: true,
  },
  {
    path: "/server/:serverId/archive/:interviewId",
    name: "archive",
    component: () => import("./views/InterviewArchive.vue"),
    props: true,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
