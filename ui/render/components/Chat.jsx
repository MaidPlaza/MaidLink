import React, { useCallback, useRef, useState, useEffect, useLayoutEffect } from 'react'
import avatarImg from '../../assets/avatars/avatar_0.png'
import messageBg from '../../assets/svgStructure/message_background.svg'
import { useUIStructure, emoteSvg, chatWindowSvgs, sidePanelSvg, sidePanelButtonSvg, messagesContainerSvg, chatBackgroundSvg, userMessageTailSvg, notificationSvg } from '@/lib/uiStructure'
import SLASH_COMMANDS from '@/electron/configs/slashCommands.json'
import WindowControls from './WindowControls'
import ChatSettings from './settings/ChatSettings'
import CharacterWardrobe from './CharacterWardrobe'
import CharacterInformation from './CharacterInformation'
import ContextModelSettings from './ContextModelSettings.jsx'
import ShaderTextLayer from '../shaders/text_shaders/ShaderTextLayer'
import { parseMarkup } from '@/lib/markup'
import { wrapCodeBlocks, splitCodeBlocks } from '@/lib/codeBlocks'
import { GESTURE_EVENT, gestureChipText, insertAtCaret, deleteTokenAt, jumpOverToken } from '@/lib/gestures'
import { editorFacade, hasRawToken, insertPlainText, renderedWidth, serializeNode } from '@/lib/richInput'
import markupConfig from '@/electron/configs/markup.json'
import { api } from '@/lib/api'
import { useSetting } from '@/lib/settings'
import { useCapability } from '@/lib/capabilities'
import { sounds } from '@/lib/sounds'
import { gachaBadgeColors, gachaButtonSvg, profileBlockTopSvg, frameAsBlockMiddle, frameAsBlockBottom } from '@/lib/gachaButton'
import GachaHowTo from './GachaHowTo'
import GachaRevealCard, { isGachaRevealed } from './GachaRevealCard'
import { markOffscreen } from '@/lib/offscreen'

const SLASH_HINTS_ENABLED = import.meta.env.DEV

const MAX_FILES_FALLBACK = 1

const SETTINGS_PANEL_MS = 300
const CHAT_CARD_CLOSE_MS = 600

const DOC_EXTS = ['.txt', '.json', '.md', '.pdf']
const IMAGE_EXTS = ['.png', '.jpg', '.jpeg']
const ATTACH_EXTS = new Set(['.txt', '.md', '.pdf'])
const DOC_TYPES = [
  'text/plain',
  'application/json',
  'text/markdown',
  'application/pdf',
]
const IMAGE_TYPES = ['image/png', 'image/jpeg']

function extOf(name = '') {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i).toLowerCase()
}

function stripQuotes(s = '') {
  const m = s.match(/^(['"«])([\s\S]*)(['"»])$/)
  return m ? m[2] : s
}

function baseOf(name = '') {
  const i = name.lastIndexOf('.')
  return i <= 0 ? name : name.slice(0, i)
}

const FILE_TYPE_ICONS = {
  '.json': (
    <svg width="23" height="24" viewBox="0 0 23 24" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V15.8125H18.6875V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6563 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25624 0.302901 4.9875 0 5.75 0L13.6563 0L20.125 6.46875ZM5.96706 21.9794C5.87252 21.7766 5.81833 21.5574 5.8075 21.3339H6.90575C6.92588 21.4461 6.96879 21.553 7.03184 21.6479C7.09489 21.7429 7.17673 21.8239 7.27231 21.8859C7.37294 21.9559 7.49273 22.0105 7.63169 22.0498C7.76777 22.0891 7.92063 22.1088 8.09025 22.1088C8.32504 22.1088 8.52294 22.0752 8.68394 22.0081C8.8305 21.9532 8.95788 21.8568 9.0505 21.7307C9.13275 21.6075 9.17492 21.4619 9.17125 21.3138C9.17512 21.2239 9.15728 21.1344 9.11925 21.0528C9.08122 20.9712 9.02411 20.9 8.95275 20.8452C8.80708 20.7302 8.58523 20.6377 8.28719 20.5677L7.39881 20.3622C7.12483 20.3048 6.86275 20.2007 6.624 20.0546C6.41269 19.9252 6.23839 19.7435 6.118 19.527C5.9976 19.2944 5.93684 19.0356 5.94119 18.7738C5.94119 18.423 6.03223 18.1168 6.21431 17.8552C6.39831 17.5945 6.65131 17.3923 6.97331 17.2486C7.29627 17.1048 7.66858 17.0334 8.09025 17.0344C8.52725 17.0344 8.90052 17.1072 9.21006 17.2529C9.52248 17.3995 9.76206 17.596 9.92881 17.8422C10.1013 18.0866 10.1971 18.3578 10.2163 18.6559H9.13819C9.11358 18.5195 9.05416 18.3917 8.96569 18.285C8.87223 18.1692 8.75041 18.0796 8.61206 18.0248C8.44364 17.9551 8.26239 17.9218 8.08019 17.9271C7.76969 17.9271 7.52435 17.9999 7.34419 18.1456C7.2595 18.2101 7.19126 18.2938 7.14505 18.3897C7.09883 18.4856 7.07594 18.5911 7.07825 18.6976C7.07825 18.8701 7.14725 19.0138 7.28525 19.1288C7.45774 19.2548 7.65613 19.3407 7.866 19.3804L8.75869 19.5859C9.0711 19.6578 9.34231 19.7589 9.57231 19.8893C9.79412 20.0104 9.98005 20.1879 10.1114 20.4039C10.2408 20.6166 10.3054 20.885 10.3054 21.2089C10.3054 21.5635 10.2154 21.8778 10.0352 22.1519C9.84484 22.4341 9.57525 22.6536 9.26038 22.7829C8.924 22.9344 8.51288 23.0101 8.027 23.0101C7.66188 23.0101 7.34323 22.9669 7.07106 22.8807C6.82067 22.8057 6.58728 22.6827 6.38394 22.5184C6.20745 22.3712 6.06519 22.1872 5.96706 21.9794ZM1.50506 21.9319C1.42512 21.7177 1.38517 21.4907 1.38719 21.2621H2.48544C2.4898 21.398 2.52625 21.531 2.59181 21.6502C2.65812 21.7629 2.75394 21.8555 2.86894 21.9178C2.98395 21.9801 3.11378 22.0098 3.24444 22.0038C3.51756 22.0038 3.71977 21.9252 3.85106 21.7681C3.98235 21.6099 4.048 21.3866 4.048 21.0982V17.1523H5.18506V21.0694C5.18506 21.7019 5.014 22.1835 4.67188 22.5141C4.33167 22.8447 3.85969 23.0101 3.25594 23.0101C2.97784 23.0148 2.7012 22.969 2.43944 22.8749C2.21939 22.7906 2.01992 22.6603 1.85438 22.4926C1.69977 22.3324 1.58073 22.1413 1.50506 21.9319ZM14.5734 19.6535V20.4039C14.5734 20.7719 14.5173 21.079 14.4052 21.3253C14.3098 21.5528 14.1486 21.7465 13.9423 21.8816C13.738 22.0029 13.5043 22.0656 13.2667 22.0627C13.0291 22.0656 12.7954 22.0029 12.5911 21.8816C12.3864 21.7454 12.2264 21.5519 12.1311 21.3253C12.0103 21.0336 11.953 20.7195 11.9629 20.4039V19.6535C11.9629 19.2836 12.0189 18.9764 12.1311 18.7321C12.2264 18.5054 12.3864 18.3119 12.5911 18.1758C12.794 18.0508 13.0284 17.9865 13.2667 17.9903C13.5206 17.9903 13.7459 18.0521 13.9423 18.1758C14.1486 18.3109 14.3098 18.5046 14.4052 18.7321C14.5173 18.9764 14.5734 19.2836 14.5734 19.6535ZM15.7277 20.3996V19.6621C15.7277 19.1207 15.6295 18.6544 15.433 18.2634C15.248 17.883 14.9524 17.5673 14.5849 17.3578C14.2207 17.147 13.7818 17.0416 13.2681 17.0416C12.7564 17.0416 12.3155 17.147 11.9456 17.3578C11.5779 17.5653 11.2825 17.8803 11.0989 18.2606C10.9025 18.6506 10.8043 19.1178 10.8043 19.6621V20.3996C10.8043 20.9381 10.9025 21.4044 11.0989 21.7982C11.2954 22.1883 11.5776 22.4882 11.9456 22.6981C12.3155 22.9061 12.7564 23.0101 13.2681 23.0101C13.7818 23.0101 14.2212 22.9061 14.5863 22.6981C14.9543 22.4873 15.2365 22.1873 15.433 21.7982C15.6285 21.4053 15.7267 20.9391 15.7277 20.3996ZM17.5821 19.0555V22.9008H16.5097V17.1523H17.4613L19.9798 20.976H20.0258V17.1523H21.1039V22.9023H20.1609L17.6295 19.0555H17.5821Z"/>
 </svg>
  ),
  '.doc': (
    <svg width="23" height="23" viewBox="0 0 23 23" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V20.125C20.125 20.8875 19.8221 21.6188 19.2829 22.1579C18.7438 22.6971 18.0125 23 17.25 23V21.5625C17.6312 21.5625 17.9969 21.411 18.2665 21.1415C18.536 20.8719 18.6875 20.5062 18.6875 20.125V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6562 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25623 0.302901 4.9875 0 5.75 0L13.6562 0L20.125 6.46875ZM8.85644 19.6449V20.3952C8.85644 20.7632 8.80038 21.0704 8.68825 21.3167C8.59291 21.5441 8.4317 21.7379 8.22538 21.873C8.02149 21.994 7.78827 22.0567 7.55119 22.0541C7.31313 22.0572 7.07885 21.9945 6.87413 21.873C6.66966 21.7372 6.50968 21.5442 6.41412 21.3181C6.29321 21.0259 6.23587 20.7113 6.24594 20.3952V19.6449C6.24594 19.275 6.302 18.9678 6.41412 18.7234C6.50944 18.4968 6.66944 18.3033 6.87413 18.1671C7.07748 18.0419 7.31242 17.9776 7.55119 17.9817C7.80419 17.9817 8.02892 18.044 8.22538 18.1686C8.43148 18.3033 8.59266 18.4965 8.68825 18.7234C8.80038 18.9678 8.85644 19.275 8.85644 19.6449ZM10.0108 20.3909V19.6535C10.0108 19.112 9.91252 18.6463 9.71606 18.2562C9.53147 17.876 9.23636 17.5604 8.86938 17.3506C8.50425 17.1398 8.06485 17.0344 7.55119 17.0344C7.0404 17.0344 6.59956 17.1398 6.22869 17.3506C5.86121 17.5578 5.5658 17.8722 5.382 18.2519C5.1865 18.641 5.08827 19.1082 5.08731 19.6535V20.3909C5.08731 20.9305 5.18554 21.3967 5.382 21.7896C5.57846 22.1787 5.86117 22.4791 6.23013 22.6909C6.60004 22.8979 7.04088 23.0014 7.55263 23.0014C8.06533 23.0014 8.50425 22.8979 8.86938 22.6909C9.23642 22.4801 9.51913 22.1797 9.7175 21.7896C9.913 21.3967 10.0108 20.9305 10.0108 20.3909ZM0 17.1436V22.8936H2.09731C2.67519 22.8936 3.15387 22.7796 3.53337 22.5515C3.91741 22.3217 4.2173 21.9745 4.38869 21.5611C4.57652 21.1298 4.67044 20.6104 4.67044 20.0028C4.67044 19.3991 4.57652 18.884 4.38869 18.4575C4.21859 18.0489 3.92114 17.706 3.54056 17.48C3.16202 17.2557 2.68094 17.1436 2.09731 17.1436H0ZM1.13706 18.0708H1.94637C2.30192 18.0708 2.59373 18.1436 2.82181 18.2893C3.05832 18.4453 3.23709 18.6745 3.33069 18.9419C3.44377 19.2314 3.50031 19.5922 3.50031 20.0244C3.50477 20.3111 3.47191 20.5971 3.40256 20.8754C3.35298 21.0954 3.25691 21.3022 3.12081 21.482C2.99574 21.6432 2.83003 21.7682 2.64069 21.8443C2.41881 21.9272 2.18319 21.9672 1.94637 21.9621H1.13563V18.0694L1.13706 18.0708ZM11.8062 18.7651C11.6996 19.0563 11.6493 19.3651 11.6581 19.6751V20.3866C11.6581 20.7403 11.7075 21.0407 11.8062 21.2879C11.8884 21.5153 12.0378 21.7123 12.2346 21.8529C12.4398 21.9825 12.679 22.0481 12.9217 22.0412C13.121 22.044 13.3183 22.0007 13.4981 21.9147C13.6585 21.8331 13.794 21.71 13.8906 21.5582C13.9881 21.3999 14.0458 21.2204 14.0587 21.0349H15.1584V21.1442C15.1446 21.4915 15.0319 21.8276 14.8336 22.1131C14.6371 22.391 14.3736 22.6085 14.0429 22.7657C13.6889 22.9283 13.3026 23.0089 12.9131 23.0014C12.3956 23.0014 11.9576 22.8979 11.5992 22.6909C11.239 22.4826 10.9522 22.1677 10.7784 21.7896C10.5925 21.3986 10.4995 20.931 10.4995 20.3866V19.6708C10.4995 19.1264 10.5939 18.6578 10.7827 18.2649C10.9696 17.871 11.2432 17.5677 11.6035 17.3549C11.9657 17.1412 12.4023 17.0344 12.9131 17.0344C13.2274 17.0344 13.5183 17.0809 13.7856 17.1738C14.054 17.2629 14.2883 17.3933 14.4886 17.5648C14.6901 17.7368 14.8538 17.9487 14.9691 18.1873C15.0844 18.4259 15.1489 18.6858 15.1584 18.9506V19.0555H14.0587C14.0453 18.8623 13.9862 18.6751 13.8862 18.5093C13.7923 18.3506 13.6565 18.2208 13.4938 18.1341C13.3184 18.0387 13.1213 17.9907 12.9217 17.9946C12.6788 17.987 12.4398 18.0564 12.2389 18.193C12.0419 18.3374 11.8915 18.5363 11.8062 18.7651Z"  />
 </svg>
  ),
  '.docx': (
    <svg width="23" height="23" viewBox="0 0 23 23" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V15.8125H18.6875V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6563 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25624 0.302901 4.9875 0 5.75 0L13.6563 0L20.125 6.46875ZM10.2939 20.3952V19.6449C10.3061 19.3291 10.2487 19.0145 10.1258 18.7234C10.0304 18.496 9.86921 18.3022 9.66288 18.1671C9.46067 18.0417 9.22658 17.9773 8.98869 17.9817C8.74978 17.978 8.51483 18.0429 8.31163 18.1686C8.10716 18.3044 7.94718 18.4973 7.85163 18.7234C7.72872 19.0145 7.67131 19.3291 7.68344 19.6449V20.3952C7.68344 20.7632 7.7395 21.0704 7.85163 21.3167C7.94694 21.5433 8.10694 21.7368 8.31163 21.873C8.51635 21.9945 8.75063 22.0572 8.98869 22.0541C9.22577 22.0567 9.45899 21.994 9.66288 21.873C9.86898 21.7383 10.0302 21.5451 10.1258 21.3181C10.2467 21.0259 10.304 20.7113 10.2939 20.3952ZM11.4483 19.6535V20.3909C11.4483 20.9305 11.35 21.3967 11.1536 21.7896C10.9675 22.1678 10.6727 22.4817 10.3069 22.6909C9.94175 22.8979 9.50235 23.0014 8.98869 23.0014C8.52847 23.0135 8.07294 22.9066 7.66619 22.6909C7.29984 22.4824 7.0048 22.1683 6.8195 21.7896C6.61333 21.3528 6.5124 20.8738 6.52481 20.3909V19.6535C6.52481 19.1082 6.62304 18.641 6.8195 18.2519C7.01596 17.8581 7.29867 17.5576 7.66763 17.3506C8.03754 17.1398 8.47838 17.0344 8.99013 17.0344C9.50283 17.0344 9.94175 17.1398 10.3069 17.3506C10.6739 17.5605 10.9566 17.8624 11.155 18.2562C11.3505 18.6453 11.4483 19.1111 11.4483 19.6535ZM1.4375 22.8922V17.1436H3.53481C4.11844 17.1436 4.6 17.2562 4.9795 17.4814C5.359 17.7047 5.64123 18.0306 5.82619 18.4589C6.01402 18.8854 6.10794 19.4 6.10794 20.0028C6.10794 20.6104 6.01402 21.1298 5.82619 21.5611C5.6374 21.9933 5.35229 22.3234 4.97088 22.5515C4.59138 22.7786 4.11269 22.8922 3.53481 22.8922H1.4375ZM3.38388 18.0708H2.57313V21.9621H3.38244C3.6479 21.9621 3.87933 21.9228 4.07675 21.8443C4.26609 21.7682 4.4318 21.6432 4.55688 21.482C4.68338 21.3191 4.77729 21.1169 4.83863 20.8754C4.90797 20.5971 4.94083 20.3111 4.93638 20.0244C4.93638 19.5931 4.87983 19.2323 4.76675 18.9419C4.67315 18.6745 4.49438 18.4453 4.25788 18.2893C4.03075 18.1436 3.73846 18.0708 3.381 18.0708H3.38388ZM13.0956 19.6751C13.0956 19.3176 13.145 19.0143 13.2437 18.7651C13.329 18.5363 13.4794 18.3374 13.6764 18.193C13.8773 18.0564 14.1163 17.987 14.3592 17.9946C14.5748 17.9946 14.7655 18.0411 14.9313 18.1341C15.0938 18.2204 15.2296 18.3497 15.3238 18.5078C15.4239 18.6741 15.4831 18.8618 15.4963 19.0555H16.5959V18.9506C16.5864 18.6858 16.5219 18.4259 16.4066 18.1873C16.2913 17.9487 16.1277 17.7368 15.9261 17.5648C15.72 17.3883 15.4804 17.2553 15.2217 17.1738C14.9414 17.0778 14.6468 17.0306 14.3506 17.0344C13.8388 17.0344 13.4023 17.1412 13.041 17.3549C12.6816 17.5677 12.408 17.871 12.2202 18.2649C12.0314 18.6578 11.937 19.1264 11.937 19.6708V20.3866C11.937 20.931 12.03 21.3986 12.2159 21.7896C12.4028 22.1787 12.6764 22.4791 13.0367 22.6909C13.3961 22.8979 13.834 23.0014 14.3506 23.0014C14.7722 23.0014 15.1484 22.9229 15.479 22.7657C15.8096 22.6085 16.0736 22.391 16.2711 22.1131C16.4694 21.8276 16.5821 21.4915 16.5959 21.1442V21.0349H15.4963C15.4833 21.2204 15.4256 21.3999 15.3281 21.5582C15.2315 21.71 15.096 21.8331 14.9356 21.9147C14.7558 22.0007 14.5585 22.044 14.3592 22.0412C14.1165 22.0481 13.8773 21.9825 13.6721 21.8529C13.4753 21.7123 13.3259 21.5153 13.2437 21.2879C13.1381 20.9995 13.0879 20.6937 13.0956 20.3866V19.6751ZM20.4154 17.1451H21.7005L19.8677 20.0287L21.6703 22.8922H20.3651L19.1432 20.8581H19.0929L17.8681 22.8922H16.629L18.4115 19.9956L16.6463 17.1436H17.986L19.182 19.2122H19.2323L20.4154 17.1451Z"  />
 </svg>
  ),
  '.md': (
    <svg width="21" height="23" viewBox="0 0 21 23" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V20.125C20.125 20.8875 19.8221 21.6188 19.2829 22.1579C18.7438 22.6971 18.0125 23 17.25 23H12.9375V21.5625H17.25C17.6312 21.5625 17.9969 21.411 18.2665 21.1415C18.536 20.8719 18.6875 20.5062 18.6875 20.125V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6562 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25623 0.302901 4.9875 0 5.75 0L13.6562 0L20.125 6.46875ZM1.01487 18.9592V22.7829H0V17.0344H1.15862L2.79737 20.7661H2.83475L4.4735 17.0344H5.6235V22.7829H4.59425V18.9592H4.53962L3.17975 22.0627H2.438L1.0695 18.9577H1.01487V18.9592ZM6.64844 22.7829V17.0344H8.74575C9.32938 17.0344 9.81094 17.1465 10.1904 17.3707C10.5699 17.595 10.8522 17.9208 11.0371 18.3482C11.224 18.7747 11.3179 19.2898 11.3189 19.8936C11.3189 20.5011 11.225 21.0206 11.0371 21.4518C10.8483 21.884 10.5632 22.2142 10.1818 22.4423C9.80231 22.6694 9.32315 22.7829 8.74431 22.7829H6.64844ZM8.59338 17.9616H7.7855V21.8529H8.59338C8.86075 21.8529 9.09267 21.8136 9.28912 21.735C9.47847 21.659 9.64418 21.534 9.76925 21.3728C9.90535 21.1929 10.0014 20.9861 10.051 20.7661C10.1152 20.5246 10.1473 20.241 10.1473 19.9151C10.1577 19.5471 10.1007 19.1802 9.97912 18.8327C9.88553 18.5653 9.70675 18.336 9.47025 18.1801C9.24217 18.0344 8.94988 17.9616 8.59338 17.9616Z"  />
 </svg>
  ),
  '.txt': (
    <svg width="21" height="23" viewBox="0 0 21 23" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V20.125C20.125 20.8875 19.8221 21.6188 19.2829 22.1579C18.7438 22.6971 18.0125 23 17.25 23H14.375V21.5625H17.25C17.6312 21.5625 17.9969 21.411 18.2665 21.1415C18.536 20.8719 18.6875 20.5062 18.6875 20.125V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6562 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25623 0.302901 4.9875 0 5.75 0L13.6562 0L20.125 6.46875ZM2.7715 22.7829V17.986H4.4045V17.0344H0V17.986H1.63012V22.7829H2.7715ZM9.51194 17.0344H8.22681L7.04375 19.1029H6.99344L5.79744 17.0344H4.45769L6.22294 19.8849L4.44044 22.7829H5.67956L6.90575 20.7489H6.95606L8.17794 22.7829H9.48175L7.68056 19.9194L9.51194 17.0344ZM12.2863 17.986V22.7829H11.1449V17.986H9.51481V17.0344H13.9193V17.986H12.2849H12.2863Z"  />
 </svg>
  ),
  '.xls': (
    <svg width="23" height="24" viewBox="0 0 23 24" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M20.125 6.46875V20.125C20.125 20.8875 19.8221 21.6188 19.2829 22.1579C18.7438 22.6971 18.0125 23 17.25 23H15.8125V21.5625H17.25C17.6312 21.5625 17.9969 21.411 18.2665 21.1415C18.536 20.8719 18.6875 20.5062 18.6875 20.125V6.46875H15.8125C15.2406 6.46875 14.6922 6.24157 14.2878 5.8372C13.8834 5.43282 13.6563 4.88437 13.6562 4.3125V1.4375H5.75C5.36875 1.4375 5.00312 1.58895 4.73353 1.85853C4.46395 2.12812 4.3125 2.49375 4.3125 2.875V15.8125H2.875V2.875C2.875 2.1125 3.1779 1.38124 3.71707 0.842068C4.25623 0.302901 4.9875 0 5.75 0L13.6562 0L20.125 6.46875ZM9.3035 21.9794C9.20896 21.7766 9.15477 21.5574 9.14394 21.3339H10.2436C10.2636 21.446 10.3063 21.5528 10.3691 21.6477C10.4319 21.7427 10.5134 21.8237 10.6088 21.8859C10.7103 21.9559 10.8301 22.0105 10.9681 22.0498C11.1052 22.0891 11.258 22.1088 11.4267 22.1088C11.6624 22.1088 11.8603 22.0752 12.0204 22.0081C12.1669 21.9532 12.2943 21.8568 12.3869 21.7307C12.4697 21.6077 12.5124 21.462 12.5091 21.3138C12.5128 21.2238 12.4948 21.1342 12.4565 21.0526C12.4182 20.971 12.3608 20.8999 12.2892 20.8452C12.1435 20.7302 11.9221 20.6377 11.6251 20.5677L10.7352 20.3622C10.4613 20.3048 10.1992 20.2007 9.96044 20.0546C9.74966 19.9251 9.57586 19.7433 9.45588 19.527C9.33547 19.2944 9.27471 19.0356 9.27906 18.7738C9.27906 18.423 9.3701 18.1168 9.55219 17.8552C9.73427 17.5945 9.98679 17.3923 10.3097 17.2486C10.6337 17.1048 11.006 17.0334 11.4267 17.0344C11.8646 17.0344 12.2384 17.1072 12.5479 17.2529C12.8584 17.3995 13.098 17.596 13.2667 17.8422C13.4392 18.0866 13.535 18.3578 13.5542 18.6559H12.4761C12.4515 18.5195 12.392 18.3917 12.3036 18.285C12.2097 18.169 12.0874 18.0794 11.9485 18.0248C11.7805 17.9553 11.5998 17.922 11.4181 17.9271C11.1066 17.9271 10.8608 17.9999 10.6806 18.1456C10.5962 18.2103 10.5282 18.294 10.4823 18.3899C10.4363 18.4858 10.4136 18.5912 10.4161 18.6976C10.4161 18.8701 10.4846 19.0138 10.6217 19.1288C10.7946 19.255 10.9935 19.3409 11.2039 19.3804L12.0951 19.5859C12.4075 19.6578 12.6787 19.7589 12.9087 19.8893C13.1306 20.0104 13.3165 20.1879 13.4478 20.4039C13.5772 20.6166 13.6419 20.885 13.6419 21.2089C13.6419 21.5635 13.5518 21.8778 13.3716 22.1519C13.1813 22.4341 12.9117 22.6536 12.5968 22.7829C12.2604 22.9344 11.8493 23.0101 11.3634 23.0101C10.9983 23.0101 10.6797 22.9669 10.4075 22.8807C10.1571 22.8057 9.92372 22.6827 9.72038 22.5184C9.54389 22.3712 9.40163 22.1872 9.3035 21.9794ZM5.07006 17.1523H3.78638L2.60187 19.2194H2.55013L1.35412 17.1523H0.01725L1.78106 20.0028L0 22.9008H1.23769L2.46387 20.8667H2.51419L3.73606 22.9008H5.04131L3.23869 20.0387L5.07006 17.1523ZM8.99013 21.9319H6.55069V17.1523H5.41506V22.9023H8.99013V21.9319Z"  />
 </svg>
  ),
  '.xlsx': (
    <svg width="19" height="24" viewBox="0 0 19 24" xmlns="http://www.w3.org/2000/svg">
 <path fillRule="evenodd" clipRule="evenodd" d="M17.9687 6.46875V15.8125H16.5312V6.46875H13.6562C13.0844 6.46875 12.5359 6.24157 12.1315 5.8372C11.7272 5.43282 11.5 4.88437 11.5 4.3125V1.4375H3.59375C3.2125 1.4375 2.84687 1.58895 2.57728 1.85853C2.3077 2.12812 2.15625 2.49375 2.15625 2.875V15.8125H0.71875V2.875C0.71875 2.1125 1.02165 1.38124 1.56082 0.842068C2.09998 0.302901 2.83125 0 3.59375 0L11.5 0L17.9687 6.46875ZM9.1425 21.3339C9.15073 21.5604 9.20627 21.7827 9.30554 21.9865C9.40482 22.1902 9.54563 22.3709 9.71894 22.517C9.90581 22.6722 10.1353 22.793 10.4075 22.8793C10.6797 22.9665 10.9983 23.0101 11.3634 23.0101C11.8493 23.0101 12.2604 22.9344 12.5968 22.7829C12.937 22.6315 13.1958 22.4207 13.3731 22.1504C13.5543 21.8698 13.6479 21.5415 13.6419 21.2074C13.6419 20.8854 13.5772 20.6171 13.4478 20.4024C13.3163 20.187 13.1304 20.01 12.9087 19.8893C12.6548 19.7482 12.381 19.6464 12.0966 19.5874L11.2039 19.3804C10.9934 19.3405 10.7945 19.254 10.6217 19.1274C10.5564 19.0766 10.5038 19.0114 10.4681 18.9368C10.4324 18.8622 10.4146 18.7803 10.4161 18.6976C10.4161 18.4733 10.5043 18.2893 10.6806 18.1456C10.8608 17.9999 11.1066 17.9271 11.4181 17.9271C11.6231 17.9271 11.8004 17.9596 11.9499 18.0248C12.0878 18.0798 12.2091 18.1694 12.3021 18.285C12.3906 18.3917 12.45 18.5195 12.4746 18.6559H13.5527C13.5346 18.3634 13.4356 18.0817 13.2667 17.8422C13.0855 17.5837 12.8369 17.3799 12.5479 17.2529C12.1951 17.0974 11.812 17.0228 11.4267 17.0344C11.005 17.0344 10.6327 17.1062 10.3097 17.25C9.98775 17.3928 9.73523 17.5945 9.55219 17.8552C9.3701 18.1168 9.27906 18.423 9.27906 18.7738C9.27906 19.0632 9.338 19.3142 9.45587 19.527C9.57375 19.7397 9.74194 19.9156 9.96044 20.0546C10.1799 20.1916 10.4386 20.2937 10.7367 20.3607L11.6251 20.5677C11.9221 20.6377 12.1435 20.7302 12.2892 20.8452C12.3608 20.8999 12.4182 20.971 12.4565 21.0526C12.4948 21.1342 12.5128 21.2238 12.5091 21.3138C12.5124 21.462 12.4697 21.6077 12.3869 21.7307C12.2943 21.8568 12.1669 21.9532 12.0204 22.0081C11.8594 22.0752 11.6615 22.1088 11.4267 22.1088C11.258 22.1088 11.1047 22.0896 10.9667 22.0513C10.8387 22.0172 10.7177 21.9612 10.6087 21.8859C10.5132 21.8239 10.4313 21.7429 10.3683 21.6479C10.3052 21.553 10.2623 21.4461 10.2422 21.3339H9.1425ZM3.78637 17.1523H5.07006L3.23869 20.0373L5.04131 22.9008H3.73606L2.51419 20.8667H2.46387L1.23769 22.9008H0L1.7825 20.0028L0.0172499 17.1523H1.35556L2.55156 19.2194H2.60331L3.78637 17.1523ZM6.55069 21.9319H8.99012V22.9008H5.41362V17.1523H6.55069V21.9319ZM17.5274 17.1523H18.8111L16.9797 20.0373L18.7824 22.9008H17.4771L16.2552 20.8667H16.2049L14.9787 22.9008H13.7411L15.5236 20.0028L13.7583 17.1523H15.0966L16.2926 19.2194H16.3444L17.5274 17.1523Z"  />
 </svg>
  ),
}

const FILE_TYPE_ICON_DEFAULT = (
  <svg width="23" height="23" viewBox="0 0 23 23" xmlns="http://www.w3.org/2000/svg">
 <path d="M7.90625 10.0625C7.71563 10.0625 7.53281 10.1382 7.39802 10.273C7.26323 10.4078 7.1875 10.5906 7.1875 10.7812C7.1875 10.9719 7.26323 11.1547 7.39802 11.2895C7.53281 11.4243 7.71563 11.5 7.90625 11.5H15.0938C15.2844 11.5 15.4672 11.4243 15.602 11.2895C15.7368 11.1547 15.8125 10.9719 15.8125 10.7812C15.8125 10.5906 15.7368 10.4078 15.602 10.273C15.4672 10.1382 15.2844 10.0625 15.0938 10.0625H7.90625ZM7.1875 13.6562C7.1875 13.4656 7.26323 13.2828 7.39802 13.148C7.53281 13.0132 7.71563 12.9375 7.90625 12.9375H15.0938C15.2844 12.9375 15.4672 13.0132 15.602 13.148C15.7368 13.2828 15.8125 13.4656 15.8125 13.6562C15.8125 13.8469 15.7368 14.0297 15.602 14.1645C15.4672 14.2993 15.2844 14.375 15.0938 14.375H7.90625C7.71563 14.375 7.53281 14.2993 7.39802 14.1645C7.26323 14.0297 7.1875 13.8469 7.1875 13.6562ZM7.1875 16.5312C7.1875 16.3406 7.26323 16.1578 7.39802 16.023C7.53281 15.8882 7.71563 15.8125 7.90625 15.8125H10.7812C10.9719 15.8125 11.1547 15.8882 11.2895 16.023C11.4243 16.1578 11.5 16.3406 11.5 16.5312C11.5 16.7219 11.4243 16.9047 11.2895 17.0395C11.1547 17.1743 10.9719 17.25 10.7812 17.25H7.90625C7.71563 17.25 7.53281 17.1743 7.39802 17.0395C7.26323 16.9047 7.1875 16.7219 7.1875 16.5312Z" />
 <path d="M13.6562 0H5.75C4.9875 0 4.25623 0.302901 3.71707 0.842068C3.1779 1.38124 2.875 2.1125 2.875 2.875V20.125C2.875 20.8875 3.1779 21.6188 3.71707 22.1579C4.25623 22.6971 4.9875 23 5.75 23H17.25C18.0125 23 18.7438 22.6971 19.2829 22.1579C19.8221 21.6188 20.125 20.8875 20.125 20.125V6.46875L13.6562 0ZM13.6562 1.4375V4.3125C13.6563 4.88437 13.8834 5.43282 14.2878 5.8372C14.6922 6.24157 15.2406 6.46875 15.8125 6.46875H18.6875V20.125C18.6875 20.5062 18.536 20.8719 18.2665 21.1415C17.9969 21.411 17.6312 21.5625 17.25 21.5625H5.75C5.36875 21.5625 5.00312 21.411 4.73353 21.1415C4.46395 20.8719 4.3125 20.5062 4.3125 20.125V2.875C4.3125 2.49375 4.46395 2.12812 4.73353 1.85853C5.00312 1.58895 5.36875 1.4375 5.75 1.4375H13.6562Z" />
 </svg>
)

function measureLineWidth(editor) {
  return renderedWidth(editor.el || editor)
}

function fmtTime(d) {
  try { return d?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) ?? '' }
  catch { return '' }
}

function fmtStats(s) {
  if (!s) return ''
  const p = []
  if (s.tokens != null) p.push(`${s.tokens} tok`)
  if (s.tps != null) p.push(`${Number(s.tps).toFixed(1)} tok/s`)
  if (s.ttft != null) p.push(`ttft ${Number(s.ttft).toFixed(1)}s`)
  if (s.total != null) {
    let t = `time ${Number(s.total).toFixed(1)}s`
    const layers = []
    if (s.prep_mood != null) layers.push(`mood ${Number(s.prep_mood).toFixed(1)}s`)
    if (s.prep_recall != null) layers.push(`mem ${Number(s.prep_recall).toFixed(1)}s`)
    if (layers.length && s.gen != null) layers.push(`main ${Number(s.gen).toFixed(1)}s`)
    if (layers.length) t += ` [ ${layers.join(' · ')} ]`
    p.push(t)
  }
  return p.join(' · ')
}

const MARKUP_RULES = markupConfig.rules || []

function GestureHandIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2" />
      <path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2" />
      <path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8" />
      <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15" />
    </svg>
  )
}

function renderRich(text) {
  const parts = splitCodeBlocks(text)
  if (parts.length === 1 && parts[0].code === undefined) return renderInline(parts[0].text)
  return parts.map((p, i) =>
    p.code !== undefined
      ? <pre key={i} className="chat-code-block" data-lang={p.lang || undefined}><code>{p.code}</code></pre>
      : <React.Fragment key={i}>{renderInline(p.text)}</React.Fragment>
  )
}

function renderInline(text) {
  const segs = parseMarkup(text, MARKUP_RULES)
  if (segs.length === 1 && !segs[0].rule) return text
  return segs.map((seg, i) =>
    seg.rule?.gesture
      ? <span key={i} className="gesture-fx"><GestureHandIcon />{gestureChipText(seg.text)}</span>
      : seg.rule?.action
      ? <span key={i} className="action-fx">{seg.text}</span>
      : seg.rule
      ? <span key={i} className="rich-fx" data-effect={seg.rule.effect} style={{ '--fx-color': seg.rule.color, fontWeight: seg.rule.weight || undefined }}>{seg.text}</span>
      : <React.Fragment key={i}>{seg.text}</React.Fragment>
  )
}

function fmtWhen(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return '' }
}

export default function Chat({ onClose, onToggleExpand, onToggleExpandAvatar, expanded, expandMode, character, characters = [], onSelectCharacter, chatAvatarUrl, portraitUrl, chat, contextWindow = 0 }) {
  const svgStructure = useUIStructure()
  const ctxFill = Math.max(0, Math.min(1, contextWindow))


  const ctxAlert = ctxFill >= 0.75
  const ctxCritical = ctxFill >= 0.9
  const containerRef = useRef(null)
  const contentRef = useRef(null)
  const borderRef = useRef(null)
  const dashedBorderRef = useRef(null)
  const inputRef = useRef(null)
  const editorRef = useCallback((node) => {
    if (inputRef.current) inputRef.current.dispose?.()
    inputRef.current = node ? editorFacade(node) : null
  }, [])
  const prevTextH = useRef(null)
  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const messagesContentRef = useRef(null)
  const offscreenRows = useRef(new Map())
  useEffect(() => {
    const box = messagesContentRef.current
    if (!box) return
    const rows = new Set(box.querySelectorAll(':scope > .chat-message'))
    const seen = offscreenRows.current
    for (const [el, stop] of seen) {
      if (!rows.has(el)) { stop(); seen.delete(el) }
    }
    for (const el of rows) {
      if (!seen.has(el)) seen.set(el, markOffscreen(el))
    }
  })
  useEffect(() => () => {
    for (const stop of offscreenRows.current.values()) stop()
    offscreenRows.current.clear()
  }, [])
  const fileInputRef = useRef(null)
  const [textValue, setTextValue] = useState('')
  const [addShifted, setAddShifted] = useState(false)
  const [slashIndex, setSlashIndex] = useState(0)
  const [slashDismissed, setSlashDismissed] = useState(false)
  const sentHistoryRef = useRef([])
  const historyIndexRef = useRef(null)
  const draftRef = useRef('')
  const { messages, sendMessage: sendChat, postFileMessage, notifyKeystroke, isGenerating, pushSystem, pushGachaCard, acknowledgeReminder, appStatus, gachaVersion } = chat

  useEffect(() => {
    function onGesture(e) {
      const token = e.detail?.token
      if (!token) return
      const el = inputRef.current
      const cur = el ? el.value : ''
      const start = el ? el.selectionStart : cur.length
      const end = el ? el.selectionEnd : start
      const { value, caret } = insertAtCaret(cur, start, end, token)
      setTextValue(value)
      requestAnimationFrame(() => {
        const t = inputRef.current
        if (t) { t.focus(); t.selectionStart = t.selectionEnd = caret }
      })
    }
    window.addEventListener(GESTURE_EVENT, onGesture)
    return () => window.removeEventListener(GESTURE_EVENT, onGesture)
  }, [])

  useEffect(() => {
    const ed = inputRef.current
    if (!ed) return
    if (ed.value !== textValue) {
      ed.value = textValue
      ed.selectionStart = ed.selectionEnd = textValue.length
    }
  }, [textValue])

  const [favorites, setFavorites] = useState({})
  const loadFavorites = useCallback(() => {
    api.gallery().then((r) => {
      if (!r || r.error) return
      setFavorites(Object.fromEntries((r.items || [])
        .filter((it) => it.source).map((it) => [it.source, it.id])))
    }).catch(() => {})
  }, [])
  useEffect(() => { loadFavorites() }, [character?.name, loadFavorites])
  useEffect(() => {
    const unsub = window.maidlink?.onGalleryChanged?.(() => loadFavorites())
    return () => { if (typeof unsub === 'function') unsub() }
  }, [loadFavorites])
  const [gacha, setGacha] = useState(null)
  const [gachaOpen, setGachaOpen] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [gachaView, setGachaView] = useState('balance')
  const [gachaHow, setGachaHow] = useState(null)
  const [gachaRevealTick, setGachaRevealTick] = useState(0)
  const onGachaRevealed = useCallback(() => setGachaRevealTick((t) => t + 1), [])
  async function openHowTo() {
    setGachaView('how')
    try {
      const r = await api.gachaAchievements()
      setGachaHow(r && !r.error ? r : null)
    } catch {
      setGachaHow(null)
    }
  }
  const loadGacha = useCallback(() => {
    api.gacha().then((r) => {
      setGacha(r && !r.error ? r : null)
    }).catch(() => setGacha(null))
  }, [])
  useEffect(() => { if (!isGenerating) loadGacha() }, [character?.name, isGenerating, loadGacha])
  useEffect(() => { if (gachaVersion) loadGacha() }, [gachaVersion, loadGacha])
  useEffect(() => { setGachaOpen(false) }, [character?.name])
  useEffect(() => {
    if (!gachaOpen) return
    const onKey = (e) => { if (e.key === 'Escape') setGachaOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [gachaOpen])
  function closeGachaFromInput() {
    if (gachaOpen) setGachaOpen(false)
  }
  async function pullTicket() {
    if (pulling) return
    setPulling(true)
    try {
      const r = await api.gachaPull()
      if (r && r.ok && r.item) {
        pushGachaCard(r.item, { unlocked: r.unlocked, total: r.total })
        const bonus = r.item.bonus_sphere
        if (bonus) {
          pushSystem(`🔮 Сфера изменения — ${bonus.category_label || 'бонус'}`
            + `${bonus.spheres ? ` (сфер: ${bonus.spheres})` : ''}.`
            + ' Открыть ею цвет вещи — в гардеробе, раздел «Стайлинг».')
        }
        setGacha((g) => ({ ...(g || {}), tickets: r.tickets, unlocked: r.unlocked, pool: r.pool, total: r.total, cap: r.cap, per_day: r.per_day, sphere_in: r.sphere_in }))
        setGachaOpen(false)
        sounds.play('notify')
      } else if (r && r.error) {
        pushSystem(r.error)
        loadGacha()
      }
    } catch {
      pushSystem('Не удалось связаться с бэкендом')
    } finally {
      setPulling(false)
    }
  }
  const profileSvg = sidePanelButtonSvg(svgStructure, 'characterInformation')
  const gachaSvg = sidePanelButtonSvg(svgStructure, 'gacha') || gachaButtonSvg(profileSvg)
  const gachaBadge = gachaBadgeColors(profileSvg)
  const favKey = (src) => String(src || '').replace(/^https?:\/\/[^/]+/, '').split('?')[0]
  const isFavoritable = (msg) => !!msg.image && !msg.youtubeId && msg.mediaKind !== 'video'
    && (msg.imageGenSeconds != null || /\/media\/generated\//.test(msg.image))
  async function toggleFavorite(msg) {
    const key = favKey(msg.image)
    const cur = favorites[key]
    try {
      if (cur) {
        const r = await api.galleryRemove(cur)
        if (r && r.ok) setFavorites((f) => { const n = { ...f }; delete n[key]; return n })
        else if (r && r.error) pushSystem(r.error)
      } else {
        const r = await api.galleryAdd(key)
        if (r && r.ok && r.item) setFavorites((f) => ({ ...f, [key]: r.item.id }))
        else if (r && r.error) pushSystem(r.error)
      }
    } catch {
      pushSystem('Не удалось связаться с бэкендом')
    }
  }
  const [showTime] = useSetting('appearance.timestamps')
  const [showStats] = useSetting('appearance.stats')
  const [maxFilesRaw] = useSetting('chat.max_files')
  const maxFiles = Number(maxFilesRaw) || MAX_FILES_FALLBACK
  const [controlsOpen, setControlsOpen] = useState(false)
  const [characterInformationOpen, setCharacterInformationOpen] = useState(false)
  const [contextModelSettingsOpen, setContextModelSettingsOpen] = useState(false)
  const [wardrobeOpen, setWardrobeOpen] = useState(false)
  const [panelSwitch, setPanelSwitch] = useState(false)
  const chatCollapsed = characterInformationOpen || contextModelSettingsOpen || wardrobeOpen
  const [messagesExpanding, setMessagesExpanding] = useState(false)
  const prevChatCollapsed = useRef(chatCollapsed)
  useLayoutEffect(() => {
    if (prevChatCollapsed.current && !chatCollapsed) setMessagesExpanding(true)
    if (chatCollapsed) setMessagesExpanding(false)
    prevChatCollapsed.current = chatCollapsed
  }, [chatCollapsed])
  const panelOpen = controlsOpen
  const chatPanelTimer = useRef(null)
  useEffect(() => () => clearTimeout(chatPanelTimer.current), [])
  const chatCards = {
    info: [characterInformationOpen, setCharacterInformationOpen],
    context: [contextModelSettingsOpen, setContextModelSettingsOpen],
    wardrobe: [wardrobeOpen, setWardrobeOpen],
  }
  function toggleChatPanel(which) {
    clearTimeout(chatPanelTimer.current)
    setGachaOpen(false)
    const [isOpen, open] = chatCards[which]
    const others = Object.keys(chatCards).filter((k) => k !== which)
    const otherOpen = others.some((k) => chatCards[k][0])

    if (isOpen) { open(false); setPanelSwitch(false); return }

    if (otherOpen) { setPanelSwitch(true); others.forEach((k) => chatCards[k][1](false)); open(true); return }

    const hadPanel = controlsOpen
    setControlsOpen(false)
    setPanelSwitch(false)
    if (hadPanel) chatPanelTimer.current = setTimeout(() => open(true), SETTINGS_PANEL_MS)
    else open(true)
  }
  function toggleSettings() {
    clearTimeout(chatPanelTimer.current)
    setGachaOpen(false)
    if (controlsOpen) { setControlsOpen(false); return }
    const cardOpen = Object.values(chatCards).some(([isOpen]) => isOpen)
    if (!cardOpen) { setControlsOpen(true); return }
    Object.values(chatCards).forEach(([, set]) => set(false))
    setPanelSwitch(false)
    chatPanelTimer.current = setTimeout(() => setControlsOpen(true), CHAT_CARD_CLOSE_MS)
  }
  function toggleGacha() {
    if (gachaOpen) { setGachaOpen(false); return }
    clearTimeout(chatPanelTimer.current)
    setControlsOpen(false)
    Object.values(chatCards).forEach(([, set]) => set(false))
    setPanelSwitch(false)
    setGachaView('balance')
    setGachaOpen(true)
  }
  const hasCharacter = characters.some((c) => c.active)
  const [systemNotificationMessage, setSystemNotificationMessage] = useState('')
  const [notificationAnimKey, setNotificationAnimKey] = useState(0)
  const [notificationShown, setNotificationShown] = useState('')
  const [notificationClosing, setNotificationClosing] = useState(false)
  const notificationCloseTimer = useRef(null)
  useEffect(() => () => clearTimeout(notificationCloseTimer.current), [])
  function showSystemNotification(message = '') {
    clearTimeout(notificationCloseTimer.current)
    setSystemNotificationMessage(message)
    if (message) {
      setNotificationShown(message)
      setNotificationClosing(false)
      setNotificationAnimKey((k) => k + 1)
      return
    }
    setNotificationClosing(true)
    notificationCloseTimer.current = setTimeout(() => {
      setNotificationShown('')
      setNotificationClosing(false)
    }, 300)
  }

  const notificationAutoTimer = useRef(null)
  useEffect(() => () => clearTimeout(notificationAutoTimer.current), [])

  const appStatusRef = useRef('')
  useEffect(() => {
    const prev = appStatusRef.current
    appStatusRef.current = appStatus || ''
    if (appStatus) {
      clearTimeout(notificationAutoTimer.current)
      showSystemNotification(appStatus)
    } else if (prev) {
      showSystemNotification('')
    }
  }, [appStatus])
  const [canScrollDown, setCanScrollDown] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [droppedFiles, setDroppedFiles] = useState([])
  const dragCounterRef = useRef(0)

  const visionAvailable = useCapability('vision')
  const VALID_TYPES = new Set(visionAvailable ? [...DOC_TYPES, ...IMAGE_TYPES] : DOC_TYPES)
  const ACCEPT_EXTS = (visionAvailable ? [...DOC_EXTS, ...IMAGE_EXTS] : DOC_EXTS).join(',')

  function hasValidFiles(dataTransfer) {
    if (!dataTransfer?.items) return false
    for (const item of dataTransfer.items) {
      if (item.kind === 'file' && (VALID_TYPES.has(item.type) || item.type === '')) return true
    }
    return false
  }

  function handleDragEnter(e) {
    e.preventDefault()
    dragCounterRef.current++
    if (hasValidFiles(e.dataTransfer)) setIsDragging(true)
  }

  function handleDragLeave(e) {
    e.preventDefault()
    dragCounterRef.current--
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDragging(false)
    }
  }

  function handleDragOver(e) {
    e.preventDefault()
  }

  function queueDocumentFile(file) {
    const path = window.maidlink?.getPathForFile?.(file)
    if (!path) return false
    setDroppedFiles(prev => {
      if (prev.length >= maxFiles) return prev
      return [...prev, { id: Date.now() + Math.random(), name: file.name,
                         kind: 'doc', path }]
    })
    return true
  }

  function intakeFile(file) {
    const ext = extOf(file.name)
    if (ATTACH_EXTS.has(ext)) {
      if (queueDocumentFile(file)) return
      if (ext === '.pdf') return
    }
    const reader = new FileReader()
    reader.onload = evt => {
      setDroppedFiles(prev => {
        if (prev.length >= maxFiles) return prev
        return [...prev, { id: Date.now() + Math.random(), name: file.name, content: evt.target.result }]
      })
    }
    if (file.type.startsWith('image/')) reader.readAsDataURL(file)
    else reader.readAsText(file)
  }

  function handleDrop(e) {
    e.preventDefault()
    dragCounterRef.current = 0
    setIsDragging(false)

    const VALID_EXTS = new Set(visionAvailable ? [...DOC_EXTS, ...IMAGE_EXTS] : DOC_EXTS)
    Array.from(e.dataTransfer.files)
      .filter(f => VALID_EXTS.has(extOf(f.name)))
      .forEach(intakeFile)
  }

  function removeDroppedFile(id) {
    setDroppedFiles(prev => prev.filter(f => f.id !== id))
  }

  function handleFileInputChange(e) {
    Array.from(e.target.files).forEach(file => {
      if (file.type.startsWith('image/') && !visionAvailable) return
      intakeFile(file)
    })
    e.target.value = ''
  }

  function handlePaste(e) {
    const items = e.clipboardData?.items
    if (!items) return
    let consumed = false
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/') && visionAvailable) {
        const file = item.getAsFile()
        if (!file) continue
        e.preventDefault()
        consumed = true
        const reader = new FileReader()
        reader.onload = evt => {
          setDroppedFiles(prev => {
            if (prev.length >= maxFiles) return prev
            return [...prev, { id: Date.now() + Math.random(), name: file.name || 'clipboard.png', content: evt.target.result }]
          })
        }
        reader.readAsDataURL(file)
      }
    }
    if (consumed) return
    const text = e.clipboardData.getData('text/plain')
    if (text) { e.preventDefault(); insertPlainText(text) }
  }

  function handleInput() {
    closeGachaFromInput()
    const ed = inputRef.current
    if (!ed) return
    const v = ed.value
    if (!v && ed.el.childNodes.length) ed.el.textContent = ''
    else if (hasRawToken(ed.el)) { const pos = ed.selectionStart; ed.value = v; ed.selectionStart = ed.selectionEnd = pos }
    setTextValue(v)
    setSlashDismissed(false)
    setSlashIndex(0)
    notifyKeystroke()
  }

  function handleCopy(e) {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return
    e.clipboardData.setData('text/plain', serializeNode(sel.getRangeAt(0).cloneContents()))
    e.preventDefault()
  }
  function handleCut(e) {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return
    handleCopy(e)
    document.execCommand('delete')
  }

  function handleEditorDrop(e) {
    if (e.dataTransfer?.files?.length) return
    e.preventDefault()
    const text = e.dataTransfer?.getData('text/plain')
    if (text) { inputRef.current?.focus(); insertPlainText(text) }
  }

  useEffect(() => {
    const ta = inputRef.current
    if (!ta) return

    const MIN_H = 30
    const MAX_H = 173
    const STACK_H = 21
    const lineH = parseFloat(getComputedStyle(ta.el).lineHeight) || 17

    ta.style.height = 'auto'
    ta.style.minHeight = '0'
    const lineCount = Math.max(1, Math.round(ta.scrollHeight / lineH))
    ta.style.minHeight = ''

    const shifted = lineCount > 1 || measureLineWidth(ta) >= 455
    setAddShifted(shifted)

    const wanted  = MIN_H + (lineCount - 1) * lineH
    const clamped = Math.min(wanted, MAX_H)
    ta.style.height = clamped + 'px'
    ta.style.overflowY = wanted > MAX_H ? 'scroll' : 'hidden'

    const h = Math.max(clamped - MIN_H, shifted ? STACK_H : 0)
    const prev = prevTextH.current
    if (prev === h) return

    ;[
      [dashedBorderRef, h + 95],
      [containerRef,    h + 95],
      [borderRef,       h + 54],
      [contentRef,      h + 48],
    ].forEach(([ref, targetH]) => {
      if (!ref.current) return
      ref.current.style.height = targetH + 'px'
    })

    if (messagesContainerRef.current) {
      messagesContainerRef.current.style.setProperty('--msgs-grow', h + 'px')
    }

    prevTextH.current = h

    if (prev === null || h <= prev) return
    const t = setTimeout(() => {
      const c = messagesContentRef.current
      if (c) c.scrollTo({ top: c.scrollHeight, behavior: 'smooth' })
      updateBottomFade()
    }, 200)
    return () => clearTimeout(t)
  }, [textValue])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const c = messagesContentRef.current
    if (c) c.scrollTo({ top: c.scrollHeight, behavior: 'smooth' })
    updateBottomFade()
  }, [messages, isGenerating, gachaRevealTick])

  function updateBottomFade() {
    const c = messagesContentRef.current
    if (c) setCanScrollDown(c.scrollHeight - c.scrollTop - c.clientHeight > 4)
  }

  useEffect(() => {
    window.maidlink?.reportChatActivity(isGenerating)
  }, [isGenerating])

  async function sendMessage() {
    const text = textValue.trim()
    const img = droppedFiles.find(f => typeof f.content === 'string' && f.content.startsWith('data:image'))
    const docs = droppedFiles.filter(f => f.kind === 'doc')
    const inlineDoc = droppedFiles.find(f => !f.kind && f.content && !String(f.content).startsWith('data:image'))
    if (!text && !img && !docs.length && !inlineDoc) return

    if (text) {
      const h = sentHistoryRef.current
      if (h[h.length - 1] !== text) h.push(text)
    }
    historyIndexRef.current = null
    draftRef.current = ''

    if (import.meta.env.DEV && (text === '/persona' || text.startsWith('/persona ') ||
        text === '/персонаж' || text.startsWith('/персонаж '))) {
      handlePersonaCommand(text)
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/axis' || text.startsWith('/axis '))) {
      handleAxisCommand(text)
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/setup' || text.startsWith('/setup '))) {
      const arg = text.slice(6).trim().toLowerCase()
      const on = arg !== 'off' && arg !== 'выкл'
      const vram = Number(arg) || 0
      api.setupMock(on, vram, arg === 'terms').then(() => window.location.reload()).catch(() => {})
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/chars' || text.startsWith('/chars '))) {
      const n = Number(text.slice(6).trim())
      api.charactersMock(Number.isFinite(n) ? n : 7)
        .then(() => window.location.reload())
        .catch(() => {})
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/state' || text === '/состояние')) {
      handleStateCommand()
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/records' || text === '/память')) {
      handleRecordsCommand()
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/prompt' || text === '/промпт')) {
      handlePromptCommand()
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/loops' || text === '/петли')) {
      handleLoopsCommand()
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/prefs' || text === '/предпочтения')) {
      handlePrefsCommand()
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/polish' || text.startsWith('/polish '))) {
      handlePolishCommand(text)
      setTextValue('')
      inputRef.current?.focus()
      return
    }
    if (import.meta.env.DEV && (text === '/sysnotification' || text.startsWith('/sysnotification '))) {
      showSystemNotification(stripQuotes(text.slice('/sysnotification'.length).trim()))
      setTextValue('')
      inputRef.current?.focus()
      return
    }

    for (const d of docs) {
      try {
        const res = await api.attachDocument(d.path, !!text)
        if (res && res.ok === false && res.error) {
          pushSystem(`Не прикрепила «${d.name}»: ${res.error}`)
        }
      } catch (err) {
        pushSystem(`Не прикрепила «${d.name}»: ${err}`)
      }
    }
    const fileForBubble = docs[0] || inlineDoc
    if (text || img) {
      sendChat(text && wrapCodeBlocks(textValue), img?.content, fileForBubble && { name: fileForBubble.name })
    } else if (fileForBubble) {
      postFileMessage(fileForBubble.name)
    }
    setTextValue('')
    setDroppedFiles([])
    inputRef.current?.focus()
  }

  function handlePersonaCommand(raw) {
    const arg = raw.trim().split(/\s+/).slice(1).join(' ').trim().toLowerCase()
    const list = characters || []
    if (!arg) {
      const names = list.map(c => `${c.id}${c.active ? '*' : ''}`).join(', ')
      pushSystem(`Персонажи: ${names || '—'}. Выбор: /persona <id>  (* — активный)`)
      return
    }
    const target = list.find(c => c.id.toLowerCase() === arg || (c.name || '').toLowerCase() === arg)
    if (!target) {
      pushSystem(`Нет персонажа «${arg}». Доступны: ${list.map(c => c.id).join(', ') || '—'}`)
      return
    }
    if (target.active) {
      pushSystem(`${target.name} уже ${target.gender === 'male' ? 'активен' : 'активна'}.`)
      return
    }
    pushSystem(`Переключаюсь на ${target.name}…`)
    onSelectCharacter?.(target.id)
  }

  async function handleAxisCommand(raw) {
    const AXES = ['trust', 'closeness', 'respect']
    const parts = raw.trim().split(/\s+/).slice(1)
    if (parts.length < 2) {
      pushSystem(`Оси отношений: ${AXES.join(', ')}. Задать: /axis <ось> <0..1> (closeness → тир → костюмы)`)
      return
    }
    const name = parts[0].toLowerCase()
    const val = parseFloat(parts[1].replace(',', '.'))
    if (!AXES.includes(name) || Number.isNaN(val)) {
      pushSystem(`Неверно. Оси: ${AXES.join(', ')}; значение 0..1. Напр.: /axis closeness 0.8`)
      return
    }
    try {
      const r = await api.setRelationshipAxes({ [name]: Math.max(0, Math.min(1, val)) })
      const axesStr = Object.entries(r.axes).map(([k, v]) => `${k} ${Number(v).toFixed(2)}`).join(', ')
      pushSystem(`Оси: ${axesStr} → тир: ${r.tier}`)
    } catch (e) {
      pushSystem(`Не удалось задать ось: ${e}`)
    }
  }

  async function handleStateCommand() {
    try {
      const idn = await api.identity()
      const cax = idn.axes || {}
      const rax = idn.relationship_axes || {}
      const charLine = Object.entries(cax).map(([k, v]) => `${k} ${Number(v).toFixed(2)}`).join(', ')
      const relLine = ['trust', 'closeness', 'respect']
        .map((a) => (rax[a] ? `${a} ${Number(rax[a].value).toFixed(2)}` : `${a} —`)).join(', ')
      const mood = idn.mood_effective?.[0] || idn.mood_state || 'ровное'
      const reaction = idn.reaction_state || ''
      const regard = (idn.relationships || []).find((r) => r.id === 'rel_master_to_me')?.text || '—'
      const active = idn.active_traits || []
      const eligible = [...(idn.eligible_vulns_not_active || []), ...(idn.eligible_strengths_not_active || [])]
      const traitLine = active.length
        ? active.map((t) => `${t.kind === 'strength' ? '＋' : '－'}${t.text}`).join('; ')
        : '—'
      console.log('%c[state]', 'color:#7B79AB;font-weight:bold',
        { 'оси характера': cax, 'оси отношений': rax, тир: idn.tier, настроение: idn.mood_effective || mood,
          'активные трейты': active, 'eligible (не активны)': eligible, 'Господин о тебе': regard })
      console.dir(idn)
      pushSystem(`Оси характера: ${charLine || '—'}`)
      pushSystem(`Оси отношений: ${relLine} → тир: ${idn.tier || '—'} · настроение: ${mood}${reaction ? ` · вспышка: ${reaction}` : ''}`)
      pushSystem(`Трейты (активные): ${traitLine}${eligible.length ? ` · eligible: ${eligible.length}` : ''}`)
      pushSystem(`Господин о тебе (как ты ощущаешь): ${regard}`)
      pushSystem(`Полный identity → DevTools-консоль`)
    } catch (e) {
      pushSystem(`Не удалось получить состояние: ${e}`)
    }
  }

  async function handleLoopsCommand() {
    try {
      const res = await api.loops()
      const loops = res.open_loops || []
      console.log(`%c[loops] ${loops.length} открытых петель`, 'color:#7B79AB;font-weight:bold')
      console.table(loops.map((l) => ({ title: l.title, kind: l.kind, subject: l.subject, salience: l.salience })))
      console.log('[loops] полные:', loops)
      if (!loops.length) { pushSystem('Открытых петель нет.'); return }
      pushSystem(`Петли (${loops.length}): ${loops.map((l) => l.title).join('; ')} → DevTools-консоль`)
    } catch (e) {
      pushSystem(`Не удалось получить петли: ${e}`)
    }
  }

  async function handlePrefsCommand() {
    try {
      const p = await api.profile()
      const prefs = p.preferences || []
      const rules = p.rules || []
      console.log('%c[prefs] профиль Господина', 'color:#7B79AB;font-weight:bold')
      console.log('summary:', p.summary || '—')
      console.log('preferences:', prefs)
      console.log('rules:', rules)
      pushSystem(`Профиль: предпочтений ${prefs.length}, правил ${rules.length}${p.summary ? ', есть summary' : ''} → DevTools-консоль`)
    } catch (e) {
      pushSystem(`Не удалось получить профиль: ${e}`)
    }
  }

  async function handleRecordsCommand() {
    try {
      const res = await api.memory()
      console.log(`%c[memory] ${res.total} записей`, 'color:#7B79AB;font-weight:bold')
      console.table(res.records.map((r) => ({ type: r.type, title: r.title, importance: r.importance })))
      console.log('[memory] полные записи:', res.records)
      pushSystem(`Память: ${res.total} записей → DevTools-консоль`)
    } catch (e) {
      pushSystem(`Не удалось получить память: ${e}`)
    }
  }

  async function handlePromptCommand() {
    try {
      const res = await api.prompt()
      console.log(`%c[prompt] ~${res.tokens_approx} токенов`, 'color:#7B79AB;font-weight:bold')
      console.log(res.prompt)
      pushSystem(`Промпт (~${res.tokens_approx} токенов) → DevTools-консоль`)
    } catch (e) {
      pushSystem(`Не удалось получить промпт: ${e}`)
    }
  }

  async function handlePolishCommand(raw) {
    const arg = raw.replace(/^\/polish\s*/i, '').trim()
    if (!arg) { pushSystem('Использование: /polish <текст> — прогнать грамма-корректор'); return }
    try {
      const r = await api.polishGrammar(arg)
      if (r.error) { pushSystem(`Корректор: ошибка — ${r.error}`); return }
      console.log('%c[polish]', 'color:#7B79AB;font-weight:bold', { original: r.original, corrected: r.corrected })
      pushSystem(`ориг: ${r.original}`)
      pushSystem(`✓ ${r.corrected}${r.corrected === r.original ? '  (без изменений)' : ''}`)
    } catch (e) {
      pushSystem(`Не удалось прогнать корректор: ${e}`)
    }
  }

  const slashActive = textValue.startsWith('/') && !textValue.includes(' ')
  const slashQuery = textValue.slice(1).toLowerCase()
  const slashMatches = SLASH_HINTS_ENABLED && slashActive
    ? SLASH_COMMANDS
        .map(c => ({ c, idx: c.command.slice(1).toLowerCase().indexOf(slashQuery) }))
        .filter(x => x.idx !== -1)
        .sort((a, b) => a.idx - b.idx || a.c.command.length - b.c.command.length)
        .map(x => x.c)
    : []
  const showSlashMenu = SLASH_HINTS_ENABLED && slashMatches.length > 0 && !slashDismissed

  function selectSlashCommand(item) {
    setTextValue(item.command + ' ')
    setSlashDismissed(true)
    setSlashIndex(0)
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) { el.focus(); el.selectionStart = el.selectionEnd = el.value.length }
    })
  }

  function handleKeyDown(e) {
    if (showSlashMenu) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSlashIndex(i => (i + 1) % slashMatches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSlashIndex(i => (i - 1 + slashMatches.length) % slashMatches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        selectSlashCommand(slashMatches[Math.min(slashIndex, slashMatches.length - 1)])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSlashDismissed(true)
        return
      }
    }
    if ((e.key === 'Backspace' || e.key === 'Delete' || e.key === 'ArrowLeft' || e.key === 'ArrowRight')
        && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
      const ta = inputRef.current
      if (ta && ta.selectionStart === ta.selectionEnd) {
        const pos = ta.selectionStart
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          const to = jumpOverToken(ta.value, pos, e.key === 'ArrowLeft' ? 'left' : 'right')
          if (to !== null) { e.preventDefault(); ta.selectionStart = ta.selectionEnd = to; return }
        } else {
          const r = deleteTokenAt(ta.value, pos, e.key === 'Backspace' ? 'back' : 'forward')
          if (r) { e.preventDefault(); setTextValue(r.value); placeCaret(r.caret); return }
        }
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
      return
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      recallHistory(e)
    }
  }

  function recallHistory(e) {
    const ta = inputRef.current
    const hist = sentHistoryRef.current
    if (!ta || hist.length === 0) return

    const caretStart = ta.selectionStart === 0 && ta.selectionEnd === 0
    const caretEnd   = ta.selectionStart === ta.value.length && ta.selectionEnd === ta.value.length

    if (e.key === 'ArrowUp') {
      if (!caretStart) return
      e.preventDefault()
      if (historyIndexRef.current === null) {
        draftRef.current = textValue
        historyIndexRef.current = hist.length - 1
      } else if (historyIndexRef.current > 0) {
        historyIndexRef.current -= 1
      }
      setTextValue(hist[historyIndexRef.current])
      moveCaretToEnd()
    } else {
      if (historyIndexRef.current === null || !caretEnd) return
      e.preventDefault()
      if (historyIndexRef.current < hist.length - 1) {
        historyIndexRef.current += 1
        setTextValue(hist[historyIndexRef.current])
      } else {
        historyIndexRef.current = null
        setTextValue(draftRef.current)
      }
      moveCaretToEnd()
    }
  }

  function moveCaretToEnd() {
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) el.selectionStart = el.selectionEnd = el.value.length
    })
  }

  function placeCaret(pos) {
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) el.selectionStart = el.selectionEnd = pos
    })
  }


  const view = messages.map((m) => ({
    key: m.id,
    role: m.role,
    text: m.content,
    time: fmtTime(m.timestamp),
    image: m.image,
    fileName: m.fileName,
    stats: m.stats,
    streaming: m.streaming,
    imageGenSeconds: m.imageGenSeconds,
    mediaKind: m.mediaKind,
    youtubeId: m.youtubeId,
    id_mood: m.id_mood ?? 0,
    reason: m.reason,
    summary: m.summary,
    mood: m.mood,
    reminderRecordId: m.reminderRecordId,
    reminderKind: m.reminderKind,
    reminderEventAtIso: m.reminderEventAtIso,
    reminderFallback: m.reminderFallback,
    reminderAcknowledged: m.reminderAcknowledged,
    gacha: m.gacha,
  }))
  const gachaHoldIdx = view.findIndex((m) => m.role === 'gacha_card' && !isGachaRevealed(m.key))
  const shownView = gachaHoldIdx < 0
    ? view
    : view.filter((m, i) => i <= gachaHoldIdx || m.role !== 'character')



  return (
    <div className="chat-drop-zone" onDragEnter={handleDragEnter} onDragLeave={handleDragLeave} onDragOver={handleDragOver} onDrop={handleDrop}>
      <div className="chat-background">
          <div className={expanded  ? "chat-background-top-block-shadow-opened" : "chat-background-top-block-shadow"}/>
          <div className="chat-background-top-block"/>
          <div className="chat-background-bottom-block"/>
          <div
            className="chat-background-svg-decoration no-select"
            dangerouslySetInnerHTML={{ __html: chatBackgroundSvg(svgStructure) }}
          />
      </div>
      {notificationShown && (
      <div key={notificationAnimKey} className={`chat-system-notification${notificationClosing ? ' is-closing' : ''}`}>
        <svg className="ml-arrow-loader arrow-loader-shadow" width="355" height="40" viewBox="0 0 280 40" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A pointed bar grows to the left, three chevrons slide in from the right and then ripple in a continuous wave">

          <style>{`
            .ml-arrow-loader .cap  { fill: var(--shape); animation: capGrow 1s ease-out forwards; }
            .ml-arrow-loader .body { fill: var(--shape); transform-box: fill-box; transform-origin: right center; animation: bodyGrow 1s ease-out forwards; }
            .ml-arrow-loader .chev { fill: var(--shape); }

            .ml-arrow-loader .chev-1 { animation: chev1 1s ease-out forwards, chevWave 1.2s linear 1.3s infinite; }
            .ml-arrow-loader .chev-2 { animation: chev2 1s ease-out forwards, chevWave 1.2s linear 1.5s infinite; }
            .ml-arrow-loader .chev-3 { animation: chev3 1s ease-out forwards, chevWave 1.2s linear 1.7s infinite; }

            @keyframes capGrow  { 0% { transform: translateX(255.5px); } 30%, 100% { transform: translateX(0); } }
            @keyframes bodyGrow { 0% { transform: scaleX(0.0173); }      30%, 100% { transform: scaleX(1); } }

            @keyframes chev1 { 0%, 34% { opacity: 0; transform: translateX(16px); } 52%, 100% { opacity: 1; transform: translateX(0); } }
            @keyframes chev2 { 0%, 52% { opacity: 0; transform: translateX(16px); } 70%, 100% { opacity: 1; transform: translateX(0); } }
            @keyframes chev3 { 0%, 70% { opacity: 0; transform: translateX(16px); } 88%, 100% { opacity: 1; transform: translateX(0); } }

            @keyframes chevWave {
              0%    { transform: translateX(0); }
              12.5% { transform: translateX(1.05px); }
              25%   { transform: translateX(1.5px); }
              37.5% { transform: translateX(1.05px); }
              50%   { transform: translateX(0); }
              62.5% { transform: translateX(-1.05px); }
              75%   { transform: translateX(-1.5px); }
              87.5% { transform: translateX(-1.05px); }
              100%  { transform: translateX(0); }
            }

            @media (prefers-reduced-motion: reduce) {
              .ml-arrow-loader .cap,
              .ml-arrow-loader .body,
              .ml-arrow-loader .chev { animation: none; opacity: 1; transform: none; }
            }
          `}</style>

          <rect className="body" x="51" y="5" width="260" height="30"/>
          <path className="cap"  d="M35.5 20 L52 5 L52 35 Z"/>

          <path className="chev chev-1" d="M30.5 20 L46 35 L41 35 L25.5 20 L41 5 L46 5 Z"/>
          <path className="chev chev-2" d="M20.5 20 L36 35 L31 35 L15.5 20 L31 5 L36 5 Z"/>
          <path className="chev chev-3" d="M10.5 20 L26 35 L21 35 L5.5 20 L21 5 L26 5 Z"/>
        </svg>
        <div className='chat-system-notification-text'>
          {notificationShown}
        </div>
        

      </div>
      )}


        <div
          className={`chat-messages-container${chatCollapsed ? ' is-character-info' : ''}${messagesExpanding ? ' is-expanding' : ''}`}
          ref={messagesContainerRef}
          onAnimationEnd={(e) => {
            if (e.target === e.currentTarget && e.animationName === 'chat-messages-container-expand') setMessagesExpanding(false)
          }}
        >
         
          <div className={`chat-messages-controller${chatCollapsed ? ' is-character-info' : ''}`}>

            <div className="chat-messages-container-background">
            </div>

            <div className='chat-messages-content' ref={messagesContentRef} onScroll={updateBottomFade}>
              <div className="chat-messages-spacer" />
                  {shownView.map((msg) => {
                    if (msg.role === 'divider') {
                      return (
                        <div key={msg.key} className="chat-message chat-message--divider">
                          <div className="chat-divider">
                            <div className="chat-divider-line">{msg.text}{msg.reason ? ` · ${msg.reason}` : ''}</div>
                            {msg.summary && <div className="chat-divider-summary">«{msg.summary}»</div>}
                            {msg.mood && <div className="chat-divider-mood">настроение: {msg.mood}</div>}
                          </div>
                        </div>
                      )
                    }
                    if (msg.role === 'reminder_card') {
                      const kindLabel = msg.reminderKind === 'pre_event' ? 'Скоро событие' : 'Напоминание'
                      const when = msg.reminderKind === 'pre_event' ? fmtWhen(msg.reminderEventAtIso) : ''
                      return (
                        <div key={msg.key} className="chat-message chat-message--reminder">
                          <div className="chat-reminder-card">
                                  <div
                                    className='chat-notification-svg-decoration  no-select'
                                    dangerouslySetInnerHTML={{ __html: notificationSvg(svgStructure, 'panel') }}
                                  />
                            <div className="chat-reminder-head">
                              <span
                                className="chat-reminder-head-icon"
                                dangerouslySetInnerHTML={{ __html: notificationSvg(svgStructure, 'icon') }}
                              />
                              <span>{kindLabel}</span>
                              {when && <span className="chat-reminder-when">{when}</span>}
                            </div>
                            <div className="chat-reminder-title">{msg.text}</div>
                            {msg.reminderFallback && (
                              <div className="chat-reminder-title chat-reminder-title--fallback">{msg.reminderFallback}</div>
                            )}
                            <button
                              className="chat-reminder-ack-button"
                              disabled={msg.reminderAcknowledged}
                              onClick={() => msg.reminderRecordId && acknowledgeReminder(msg.reminderRecordId)}
                            >
                              {msg.reminderAcknowledged ? '✓ Прочитано' : 'Прочитано'}
                            </button>
            
                          </div>
                        

                        </div>
                      )
                    }
                    if (msg.role === 'gacha_card') {
                      return (
                        <div key={msg.key} className="chat-message chat-message--gacha no-select">
                          <GachaRevealCard
                            id={msg.key}
                            item={{ label: msg.text, ...(msg.gacha || {}) }}
                            onRevealed={onGachaRevealed}
                          />
                        </div>
                      )
                    }
                    if (msg.role === 'system') {
                      return (
                        <div key={msg.key} className="chat-message chat-message--system">
                          <div className="chat-message-system-pill">{msg.text}</div>
                        </div>
                      )
                    }
                    if (msg.role === 'user') {
                      return (
                      
                      <div key={msg.key} className="chat-message chat-message--user">
                      {
                        msg.image?
                        <div className="chat-message-bubble-wrap">
                        
                          <div className="chat-message-bubble-picture">
                          {msg.image && <img className="chat-message-image" src={msg.image} alt="" onLoad={() => messagesContentRef.current?.scrollTo({ top: messagesContentRef.current.scrollHeight })} />}
                          </div>
                          <div className="chat-message-bubble-area">
                            <div className="chat-message-bubble-picture-text">
                              <span className="chat-message-text">{renderRich(msg.text)}</span>
                            </div>
                            <div className="chat-message-tail"
                            dangerouslySetInnerHTML={{ __html: userMessageTailSvg(svgStructure) }}
                            />

                          
                          </div>
                          {showTime && <span className="chat-message-time">{msg.time}</span>}
                        </div> 
                        :
                        
                        
                          msg.fileName?
                            <div className="chat-message-bubble-wrap">
                          
                            <div className="chat-message-bubble-file">
                              <div className='chat-message-bubble-file-name'>
                                {baseOf(msg.fileName)}
                              </div>
                              <div className="chat-message-bubble-file-type">
                                {FILE_TYPE_ICONS[extOf(msg.fileName)] || FILE_TYPE_ICON_DEFAULT}
                              </div>
                            
                            </div>
                            <div className="chat-message-bubble-area">
                              <div className="chat-message-bubble">
                                <span className="chat-message-text">{renderRich(msg.text)}</span>
                              </div>
                              <div className="chat-message-tail"
                              dangerouslySetInnerHTML={{ __html: userMessageTailSvg(svgStructure) }}
                              />
                            </div>
                            {showTime && <span className="chat-message-time">{msg.time}</span>}
                          </div> 
                          :

                        <div className="chat-message-bubble-wrap">
                        
                          <div className="chat-message-bubble-area">
                            <div className="chat-message-bubble">
                              {msg.image && <img className={`chat-message-image chat-message-image--inline${msg.text ? ' chat-message-image--captioned' : ''}`} src={msg.image} alt="" onLoad={() => messagesContentRef.current?.scrollTo({ top: messagesContentRef.current.scrollHeight })} />}
                              <span className="chat-message-text">{renderRich(msg.text)}</span>
                            </div>
                            <div className="chat-message-tail"
                              dangerouslySetInnerHTML={{ __html: userMessageTailSvg(svgStructure) }}
                              />
                          </div>
                          {showTime && <span className="chat-message-time">{msg.time}</span>}
                        </div> 
                      

                      }
                      
                      </div>
                      )
                    }
                    const meta = [showTime ? msg.time : '', showStats ? fmtStats(msg.stats) : ''].filter(Boolean).join(' · ')
                    return (
                      <div key={msg.key} className={`chat-message chat-message--ai${msg.youtubeId ? ' chat-message--video' : ''}`}>
                        <div className="chat-message-ai-avatar-wrap no-select">

                          <div className="chat-message-ai-avatar">
                            <img src={chatAvatarUrl || avatarImg} alt="avatar" onError={(e) => { e.currentTarget.src = avatarImg }} />
                          </div>
                          {!msg.streaming && emoteSvg(svgStructure, msg.id_mood) && (
                            <div
                              className="chat-message-ai-mood"
                              dangerouslySetInnerHTML={{ __html: emoteSvg(svgStructure, msg.id_mood) }}
                            />
                          )}
                        </div>

                        {(msg.image || msg.youtubeId)?
                          <div className={`chat-message-ai-col${msg.youtubeId ? ' chat-message-ai-col--video' : ''}`}>
                            <div className={`chat-message-ai-bubble-picture${msg.youtubeId ? ' chat-message-ai-bubble-picture--video' : ''}`}>
                              {msg.youtubeId
                                ? <iframe
                                    className="chat-message-video-embed"
                                    src={`https://www.youtube-nocookie.com/embed/${msg.youtubeId}`}
                                    title="YouTube"
                                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                    allowFullScreen
                                  />
                                : msg.mediaKind === 'video'
                                ? <video className={`chat-message-image${msg.text ? ' chat-message-image--captioned' : ''}`} src={msg.image} controls loop
                                    onLoadedData={() => messagesContentRef.current?.scrollTo({ top: messagesContentRef.current.scrollHeight })} />
                                : msg.image && <img className={`chat-message-image${msg.text ? ' chat-message-image--captioned' : ''}`} src={msg.image} alt="" onLoad={() => messagesContentRef.current?.scrollTo({ top: messagesContentRef.current.scrollHeight })} />}
                              {isFavoritable(msg) && (
                                <button
                                  type="button"
                                  className={`chat-image-fav${favorites[favKey(msg.image)] ? ' is-on' : ''}`}
                                  title={favorites[favKey(msg.image)] ? 'В галерее — убрать' : 'В галерею персонажа'}
                                  onClick={(e) => { e.stopPropagation(); toggleFavorite(msg) }}
                                >
                                  <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                                    <path d="M12 21s-7.5-4.6-9.6-9.1C1 8.6 3 5.5 6.2 5.1c1.9-.2 3.6.7 4.6 2.1 1-1.4 2.7-2.3 4.6-2.1 3.2.4 5.2 3.5 3.8 6.8C19.5 16.4 12 21 12 21z" />
                                  </svg>
                                </button>
                              )}
                            </div>
                            {(showTime || msg.imageGenSeconds != null) && (
                              <span className="chat-message-ai-meta chat-message-ai-meta--shown">
                                {[showTime ? msg.time : '',
                                  msg.imageGenSeconds != null
                                    ? `time ${Number(msg.imageGenSeconds).toFixed(1)}s`
                                    : ''].filter(Boolean).join(' · ')}
                              </span>
                            )}
                          </div>
                        :
                          <div className="chat-message-ai-col">
                            <div className="chat-message-ai-bubble">

                              {msg.image && <img className={`chat-message-image chat-message-image--inline${msg.text ? ' chat-message-image--captioned' : ''}`} src={msg.image} alt="" onLoad={() => messagesContentRef.current?.scrollTo({ top: messagesContentRef.current.scrollHeight })} />}
                              <span className="chat-message-ai-bubble-text">{renderRich(msg.text)}</span>
                            </div>
                            {meta && <span className="chat-message-ai-meta chat-message-ai-meta--shown">{meta}</span>}
                          </div>
                        }

                        
                      </div>
                    )
                  })}
                  {isGenerating && gachaHoldIdx < 0 && !view[view.length - 1]?.streaming && (
                    <div className="chat-message chat-message--ai">
                      <div className="chat-message-ai-avatar-wrap">

                        <div className="chat-message-ai-avatar">
                          <img src={chatAvatarUrl || avatarImg} alt="avatar" onError={(e) => { e.currentTarget.src = avatarImg }} />
                        </div>
                      </div>
                      <div className="chat-message-ai-bubble chat-message-ai-bubble--thinking">
                        <span className="chat-message-dots"><span/><span/><span/></span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />

            </div>

            <ShaderTextLayer scrollRef={messagesContentRef} />

            <div className="chat-messages-fade-top" />
            <div className={`chat-messages-fade-bottom${canScrollDown ? ' chat-messages-fade-bottom--visible' : ''}`} />
            
          </div>
          
          <div className={`chat-character-information-container${characterInformationOpen ? ' is-open' : ''}${panelSwitch ? ' is-switch' : ''}`}>
              {characterInformationOpen?
              <CharacterInformation portraitUrl={portraitUrl} />
              :  
              ""
              }
            
          </div>

          <div className={`chat-context-model-settings-container${contextModelSettingsOpen ? ' is-open' : ''}${panelSwitch ? ' is-switch' : ''}`}>
              {contextModelSettingsOpen?
              <ContextModelSettings/>
              :  
              ""
              }
            
          </div>

          <div className={`chat-character-wardrobe-container${wardrobeOpen ? ' is-open' : ''}${panelSwitch ? ' is-switch' : ''}`}>
              {wardrobeOpen?
              <CharacterWardrobe />
              :
              ""
              }
          </div>
          
          
          
          <div className="chat-messages-container-svg-decorations  no-select">
            <div
              className='chat-messages-container-svg-decorations-area-bottom'
              dangerouslySetInnerHTML={{ __html: messagesContainerSvg(svgStructure, 'bottom') }}
            />
            <div
              className='chat-messages-container-svg-decorations-area-top'
              dangerouslySetInnerHTML={{ __html: messagesContainerSvg(svgStructure, 'top') }}
            />
            <div
              className='chat-messages-container-svg-decorations-area-left'
              dangerouslySetInnerHTML={{ __html: messagesContainerSvg(svgStructure, 'left') }}
            />
            <div
              className='chat-messages-container-svg-decorations-area-right'
              dangerouslySetInnerHTML={{ __html: messagesContainerSvg(svgStructure, 'right') }}
            />
          </div>

         
        </div>
    
      
      <div
        className={panelOpen || gachaOpen ? 'chat-blocker' : 'chat-blocker-closed'}
        onClick={gachaOpen ? () => setGachaOpen(false) : undefined}
      />

      <div className="chat-gacha-layer">
        {gacha && (
          <div
            className={`chat-gacha-popover no-select${gachaOpen ? ' is-open' : ''}${gachaView === 'how' ? ' is-wide' : ''}`}
            role="dialog"
            aria-label="Билеты удачи"
            aria-hidden={!gachaOpen}
            inert={!gachaOpen}
          >
            {gachaView === 'how' ? (
              <GachaHowTo data={gachaHow} onBack={() => setGachaView('balance')} />
            ) : (
              <>
                <div className="chat-gacha-popover-title">Билеты удачи</div>
                <div className="chat-gacha-popover-count">
                  <b>{gacha.tickets || 0}</b> из {gacha.cap || 7}
                </div>
                <div className="chat-gacha-popover-note">
                  Каждый день приходит билетов: {gacha.per_day || 3}, копятся до {gacha.cap || 21}. Билет открывает случайную обновку для образа, каждый {gacha.sphere_every || 25}-й — ещё и сферу изменения.
                </div>
                <div className="chat-gacha-popover-progress">
                  Открыто {gacha.unlocked || 0} из {gacha.total || 0}
                  {gacha.achievements ? ` · достижений ${gacha.achievements.earned || 0} из ${gacha.achievements.total || 0}` : ''}
                  {gacha.sphere_in ? ` · до сферы: ${gacha.sphere_in}` : ''}
                </div>
                <button
                  className="chat-gacha-popover-btn"
                  disabled={!((gacha.tickets || 0) > 0) || pulling || gacha.pool === 0}
                  onClick={pullTicket}
                >
                  {pulling ? 'Открываем…' : (gacha.pool === 0 ? 'Коллекция собрана' : 'Открыть билет')}
                </button>
                <button className="chat-gacha-popover-link" onClick={openHowTo}>Как получить билеты?</button>
              </>
            )}
          </div>
        )}
      </div>



      <div className='chat-controls-container'>
        <div className={panelOpen ? 'chat-controls-content-opened' : 'chat-controls-content'}>
              <div className='chat-controls-container-buttons'>


                <button
                  className={`chat-controls-button chat-controls-button-character-information-toggle${hasCharacter ? '' : ' chat-controls-button--disabled'}${characterInformationOpen ? ' chat-controls-button--selected' : ''}`}
                  onClick={() => toggleChatPanel('info')}
                  disabled={!hasCharacter}
                  title={hasCharacter ? undefined : 'Сначала выбери персонажа'}
                  dangerouslySetInnerHTML={{ __html: profileBlockTopSvg(profileSvg) }}
                />
                <button
                  className={`chat-controls-button chat-controls-button-wardrobe${hasCharacter ? '' : ' chat-controls-button--disabled'}${wardrobeOpen ? ' chat-controls-button--selected' : ''}`}
                  onClick={() => toggleChatPanel('wardrobe')}
                  disabled={!hasCharacter}
                  title={hasCharacter ? undefined : 'Сначала выбери персонажа'}
                  dangerouslySetInnerHTML={{ __html: frameAsBlockMiddle(sidePanelButtonSvg(svgStructure, 'wardrobe')) }}
                />
                <div className="chat-controls-gacha">
                  <button
                    className={`chat-controls-button chat-controls-button-gacha${hasCharacter && gacha ? '' : ' chat-controls-button--disabled'}${gachaOpen ? ' chat-controls-button--selected' : ''}`}
                    onClick={toggleGacha}
                    disabled={!hasCharacter || !gacha}
                    title={hasCharacter ? 'Билеты удачи' : 'Сначала выбери персонажа'}
                    dangerouslySetInnerHTML={{ __html: gachaSvg }}
                  />
                  {hasCharacter && gacha && (gacha.tickets || 0) > 0 && (
                    <span className="chat-controls-gacha-badge no-select" style={gachaBadge}>{gacha.tickets}</span>
                  )}
                </div>





                <button
                  className={`chat-controls-button chat-controls-button-settings-toggle${controlsOpen ? ' chat-controls-button--selected' : ''}`}
                  onClick={toggleSettings}
                  dangerouslySetInnerHTML={{ __html: sidePanelButtonSvg(svgStructure, 'toggle') }}
                />
                <button
                  className={`chat-controls-button chat-controls-button-context-model-toggle${contextModelSettingsOpen ? ' chat-controls-button--selected' : ''}`}
                  onClick={() => toggleChatPanel('context')}
                  dangerouslySetInnerHTML={{ __html: frameAsBlockBottom(sidePanelButtonSvg(svgStructure, 'contextModel')) }}
                />





                <button
                  className={`chat-controls-button chat-controls-button-avatar-toggle${hasCharacter ? '' : ' chat-controls-button--disabled'}${expandMode === 'avatar' ? ' chat-controls-button--selected' : ''}`}
                  onClick={onToggleExpandAvatar}
                  disabled={!hasCharacter}
                  title={hasCharacter ? undefined : 'Сначала выбери персонажа'}
                  dangerouslySetInnerHTML={{ __html: sidePanelButtonSvg(svgStructure, 'avatarToggle') }}
                />
                <button
                className={`chat-controls-button-expand${hasCharacter ? '' : ' chat-controls-button--disabled'}`}
                onClick={onToggleExpand}
                disabled={!hasCharacter}
                title={hasCharacter ? undefined : 'Сначала выбери персонажа'}
                dangerouslySetInnerHTML={{ __html: sidePanelButtonSvg(svgStructure, 'expand') }}
              />
              </div>

              <div className={controlsOpen ? 'no-select chat-controls-settings-open' : 'no-select chat-controls-settings'}>
                <ChatSettings open={controlsOpen} />
              </div>


              

        </div>

        <div className="chat-controls-svg-decorations no-select">
                <div
                  className={panelOpen ? 'chat-controls-svg-corner-opened' : 'chat-controls-svg-corner'}
                  dangerouslySetInnerHTML={{ __html: sidePanelSvg(svgStructure, 'corner') }}
                />

                <div
                  className={panelOpen ? 'chat-controls-svg-border-opened' : 'chat-controls-svg-border'}
                  dangerouslySetInnerHTML={{ __html: sidePanelSvg(svgStructure, 'border') }}
                />

        </div>
       
      </div>
      
      <div className="chat-svg-decorations  no-select">
            {chatWindowSvgs(svgStructure).map(([cls, markup]) => (
              <div key={cls} className={cls} dangerouslySetInnerHTML={{ __html: markup }} />
            ))}
      </div>
      <div className="chat-header no-select">
          {hasCharacter ? (character?.name?.toUpperCase() || 'MIRA') : ''}

      </div>
      <div
        className={`chat-textbox-container${chatCollapsed ? ' is-character-info' : ''}`}
        ref={containerRef}
      >

        {showSlashMenu && (
          <div className="chat-slash-menu">
            {slashMatches.map((item, i) => (
              <div
                key={item.command}
                className={`chat-slash-menu-item${i === slashIndex ? ' chat-slash-menu-item--active' : ''}`}
                onMouseDown={e => { e.preventDefault(); selectSlashCommand(item) }}
                onMouseEnter={() => setSlashIndex(i)}
              >
                <span className="chat-slash-menu-command">{item.command}</span>
                {item.description && <span className="chat-slash-menu-desc">{item.description}</span>}
              </div>
            ))}
          </div>
        )}

        <div className="chat-textbox-content-border" ref={borderRef} >
          <div className="chat-textbox-content" ref={contentRef} >
            <div
              ref={editorRef}
              className="chat-textbox-input"
              contentEditable
              suppressContentEditableWarning
              role="textbox"
              aria-multiline="true"
              data-placeholder="Напишите сообщение..."
              spellCheck
              onInput={handleInput}
              onFocus={closeGachaFromInput}
              onMouseDown={closeGachaFromInput}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              onCopy={handleCopy}
              onCut={handleCut}
              onDrop={handleEditorDrop}
            />
            
          </div>
          <div className="chat-textbox-buttons">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_EXTS}
              multiple
              className="chat-textbox-file-input"
              onChange={handleFileInputChange}
            />
            <button className={`chat-textbox-btn chat-textbox-btn-add${addShifted ? ' chat-textbox-btn-add--shifted' : ''}`} onClick={() => fileInputRef.current?.click()}>
              <svg width="18" height="18" viewBox="0 0 18 18">
                <path d="M9 3v12M3 9h12" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>
            <button className="chat-textbox-btn chat-textbox-btn-send" onClick={sendMessage}>
              <svg width="18" height="18" viewBox="0 0 18 18" fill='none'>
                <path  d="M9 14V4M4 9l5-5 5 5"  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
        </div>

            <div
              className={`chat-context-bar no-select${ctxAlert ? ' chat-context-bar--alert' : ''}${ctxCritical ? ' chat-context-bar--critical' : ''}`}
              data-pct={`Окно диалога ${Math.round(ctxFill * 100)}%`}
              role="progressbar"
              aria-label="Окно диалога"
              aria-valuenow={Math.round(ctxFill * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
               <div className="chat-context-bar-fill" style={{ width: `${ctxFill * 100}%` }} />
          </div>
        </div>

        <div className="chat-textbox-footer inter-footer no-select">
            Нажмите Enter для отправки, Shift+Enter для новой строки
        </div>
         <div className={`chat-textbox-content-dropped-items-container${isDragging ? ' chat-textbox-content-dropped-items-container--hidden' : ''}`}>
           {droppedFiles.map(file => (
             <div key={file.id} className='chat-textbox-content-dropped-item'>
               <div>{(() => { const dot = file.name.lastIndexOf('.'); const base = dot > 0 ? file.name.slice(0, dot) : file.name; const ext = dot > 0 ? file.name.slice(dot) : ''; return base.length > 8 ? base.slice(0, 8) + '... ' + ext : file.name })()}</div>
               <button className='chat-textbox-content-dropped-item-delete' onClick={() => removeDroppedFile(file.id)}>
                 X
               </button>
             </div>
           ))}
        </div>
      </div>

      <div className={`chat-textbox-dashed-border-wrapper${chatCollapsed ? ' is-character-info' : ''}`}>
            <div className="chat-textbox-content-dashed-border" ref={dashedBorderRef} />
      </div>

      <div className={`chat-textbox-container-item-dropper${isDragging ? ' chat-textbox-container-item-dropper--active' : ''}`}>
         <div className="chat-textbox-container-item-dropper-border no-select">
              drop file here
         </div >
      </div >

      <div className="window-controls-container">
        <WindowControls onToggleExpand={onToggleExpand} />
      </div>
  
        
    </div>
  )
}
