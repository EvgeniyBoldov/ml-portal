import{j as c}from"./index-By90sLri.js";const a="_skeleton_vq7ii_1",r="_text_vq7ii_14",v="_short_vq7ii_19",q="_medium_vq7ii_23",b="_long_vq7ii_27",k="_circle_vq7ii_31",m="_rectangle_vq7ii_37",u="_avatar_vq7ii_42",d="_button_vq7ii_48",g="_badge_vq7ii_54",x="_card_vq7ii_60",T="_table_vq7ii_66",p="_skeletonList_vq7ii_76",$="_horizontal_vq7ii_82",y="_grid_vq7ii_88",f="_skeletonTable_vq7ii_94",R="_skeletonTableRow_vq7ii_98",j="_skeletonTableCell_vq7ii_109",z="_actions_vq7ii_113",C="_numeric_vq7ii_128",o={skeleton:a,"skeleton-loading":"_skeleton-loading_vq7ii_1",text:r,short:v,medium:q,long:b,circle:k,rectangle:m,avatar:u,button:d,badge:g,card:x,table:T,skeletonList:p,horizontal:$,grid:y,skeletonTable:f,skeletonTableRow:R,skeletonTableCell:j,actions:z,numeric:C};function S({variant:n="text",size:i="medium",width:e,height:t,className:_="",style:s={}}){const l={...s,...e&&{width:typeof e=="number"?`${e}px`:e},...t&&{height:typeof t=="number"?`${t}px`:t}};return c.jsx("div",{className:`
        ${o.skeleton}
        ${o[n]}
        ${n==="text"?o[i]:""}
        ${_}
      `,style:l})}export{S};
